//! Per-request S3 metrics, recorded by an SDK interceptor.
//!
//! Filesystem-level stats show how long a `read` took; these show what S3 did
//! underneath it: which API calls ran, how many attempts (retries) they took,
//! how long each took end to end, and how they ended. Labels are bounded (API
//! operation and outcome only), never keys, buckets or mounts.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use aws_sdk_s3::config::interceptors::{
    BeforeSerializationInterceptorContextRef, BeforeTransmitInterceptorContextRef,
    FinalizerInterceptorContextRef,
};
use aws_sdk_s3::config::{ConfigBag, Intercept, RuntimeComponents};
use aws_smithy_runtime_api::box_error::BoxError;
use aws_smithy_runtime_api::client::orchestrator::{Metadata, OrchestratorError};
use aws_smithy_types::config_bag::{Storable, StoreReplace};

use opentelemetry::KeyValue;

use crate::metrics::duration::DurationMetrics;
use crate::metrics::{RagfsMetric, RagfsMetricValue};

/// How one S3 API call ended, after any retries.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) enum Outcome {
    Success,
    /// 4xx, including expected answers such as 404 on HEAD or 412 on a conditional write.
    ClientError,
    /// 5xx or 429 (throttling).
    ServerError,
    Timeout,
    /// Connection failures and unreadable responses.
    Network,
}

impl Outcome {
    fn as_str(self) -> &'static str {
        match self {
            Self::Success => "success",
            Self::ClientError => "client_error",
            Self::ServerError => "server_error",
            Self::Timeout => "timeout",
            Self::Network => "network",
        }
    }
}

#[derive(Default)]
struct OperationTotals {
    outcomes: BTreeMap<Outcome, u64>,
    attempts: u64,
}

/// Request counters for one S3 client (one mount).
#[derive(Default)]
pub(crate) struct S3RequestMetrics {
    operations: Mutex<BTreeMap<String, OperationTotals>>,
    /// End-to-end call durations, one series per `operation` attribute.
    durations: DurationMetrics,
    inflight: AtomicUsize,
}

impl S3RequestMetrics {
    fn record_attempt(&self, operation: &str) {
        let mut operations = self.operations.lock().unwrap_or_else(|e| e.into_inner());
        let totals = operations.entry(operation.to_string()).or_default();
        totals.attempts = totals.attempts.saturating_add(1);
    }

    pub(crate) fn record(&self, operation: &str, outcome: Outcome, elapsed: Duration) {
        let mut operations = self.operations.lock().unwrap_or_else(|e| e.into_inner());
        let totals = operations.entry(operation.to_string()).or_default();
        let count = totals.outcomes.entry(outcome).or_default();
        *count = count.saturating_add(1);
        drop(operations);
        self.durations
            .record(elapsed, &[KeyValue::new("operation", operation.to_string())]);
    }

    /// Native metric records for this client.
    pub(crate) fn snapshot(&self) -> Vec<RagfsMetric> {
        let operations = self.operations.lock().unwrap_or_else(|e| e.into_inner());
        let mut metrics = vec![RagfsMetric {
            name: "ragfs_s3_inflight_requests".into(),
            labels: BTreeMap::new(),
            value: RagfsMetricValue::Gauge(self.inflight.load(Ordering::Relaxed) as f64),
        }];
        for (operation, totals) in operations.iter() {
            for (outcome, count) in &totals.outcomes {
                metrics.push(RagfsMetric::counter(
                    "ragfs_s3_requests_total",
                    &[("operation", operation), ("outcome", outcome.as_str())],
                    *count,
                    1.0,
                ));
            }
            metrics.push(RagfsMetric::counter(
                "ragfs_s3_attempts_total",
                &[("operation", operation)],
                totals.attempts,
                1.0,
            ));
        }
        for point in self.durations.snapshot() {
            metrics.push(RagfsMetric {
                name: "ragfs_s3_request_duration_seconds".into(),
                labels: point
                    .attributes()
                    .map(|attribute| (attribute.key.to_string(), attribute.value.to_string()))
                    .collect(),
                value: RagfsMetricValue::Histogram {
                    bucket_bounds: point.bounds().map(|bound| bound as u64).collect(),
                    bucket_counts: point.bucket_counts().collect(),
                    count: point.count(),
                    sum: point.sum(),
                    scale: 1e-9,
                },
            });
        }
        metrics
    }
}

/// Start of one SDK operation execution (all attempts).
#[derive(Debug, Clone)]
struct ExecutionStart(Instant);

impl Storable for ExecutionStart {
    type Storer = StoreReplace<Self>;
}

/// Records every S3 call made through the client it is registered on.
#[derive(Debug)]
pub(crate) struct MetricsInterceptor(pub(crate) Arc<S3RequestMetrics>);

impl std::fmt::Debug for S3RequestMetrics {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("S3RequestMetrics")
    }
}

fn operation_name(cfg: &ConfigBag) -> String {
    cfg.load::<Metadata>()
        .map(|meta| meta.name().to_string())
        .unwrap_or_else(|| "unknown".to_string())
}

fn outcome_of<E>(error: &OrchestratorError<E>, status: Option<u16>) -> Outcome {
    if error.is_timeout_error()
        || error
            .as_connector_error()
            .is_some_and(|connector| connector.is_timeout())
    {
        return Outcome::Timeout;
    }
    match status {
        Some(429) => Outcome::ServerError,
        Some(code) if code >= 500 => Outcome::ServerError,
        Some(code) if code >= 400 => Outcome::ClientError,
        _ => Outcome::Network,
    }
}

impl Intercept for MetricsInterceptor {
    fn name(&self) -> &'static str {
        "ragfs-s3-request-metrics"
    }

    fn read_before_execution(
        &self,
        _context: &BeforeSerializationInterceptorContextRef<'_>,
        cfg: &mut ConfigBag,
    ) -> Result<(), BoxError> {
        self.0.inflight.fetch_add(1, Ordering::Relaxed);
        cfg.interceptor_state()
            .store_put(ExecutionStart(Instant::now()));
        Ok(())
    }

    fn read_before_attempt(
        &self,
        _context: &BeforeTransmitInterceptorContextRef<'_>,
        _runtime_components: &RuntimeComponents,
        cfg: &mut ConfigBag,
    ) -> Result<(), BoxError> {
        self.0.record_attempt(&operation_name(cfg));
        Ok(())
    }

    fn read_after_execution(
        &self,
        context: &FinalizerInterceptorContextRef<'_>,
        _runtime_components: &RuntimeComponents,
        cfg: &mut ConfigBag,
    ) -> Result<(), BoxError> {
        let elapsed = cfg
            .load::<ExecutionStart>()
            .map(|start| start.0.elapsed())
            .unwrap_or_default();
        let status = context
            .response()
            .map(|response| response.status().as_u16());
        let outcome = match context.output_or_error() {
            Some(Ok(_)) => Outcome::Success,
            Some(Err(error)) => outcome_of(error, status),
            None => Outcome::Network,
        };
        self.0.record(&operation_name(cfg), outcome, elapsed);
        self.0.inflight.fetch_sub(1, Ordering::Relaxed);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value(
        metrics: &[RagfsMetric],
        name: &str,
        labels: &[(&str, &str)],
    ) -> Option<RagfsMetricValue> {
        metrics
            .iter()
            .find(|m| {
                m.name == name
                    && m.labels.len() == labels.len()
                    && labels
                        .iter()
                        .all(|(k, v)| m.labels.get(*k).map(String::as_str) == Some(*v))
            })
            .map(|m| m.value.clone())
    }

    #[test]
    fn snapshot_reports_outcomes_attempts_and_durations_per_operation() {
        let metrics = S3RequestMetrics::default();
        metrics.record_attempt("GetObject");
        metrics.record_attempt("GetObject");
        metrics.record("GetObject", Outcome::Success, Duration::from_millis(3));
        metrics.record_attempt("HeadObject");
        metrics.record("HeadObject", Outcome::ClientError, Duration::from_millis(1));

        metrics.inflight.store(2, Ordering::Relaxed);
        let snapshot = metrics.snapshot();

        assert_eq!(
            value(
                &snapshot,
                "ragfs_s3_requests_total",
                &[("operation", "GetObject"), ("outcome", "success")]
            ),
            Some(RagfsMetricValue::Counter {
                value: 1,
                scale: 1.0
            })
        );
        assert_eq!(
            value(
                &snapshot,
                "ragfs_s3_attempts_total",
                &[("operation", "GetObject")]
            ),
            Some(RagfsMetricValue::Counter {
                value: 2,
                scale: 1.0
            })
        );
        assert_eq!(
            value(
                &snapshot,
                "ragfs_s3_requests_total",
                &[("operation", "HeadObject"), ("outcome", "client_error")]
            ),
            Some(RagfsMetricValue::Counter {
                value: 1,
                scale: 1.0
            })
        );
        let Some(RagfsMetricValue::Histogram { count, sum, .. }) = value(
            &snapshot,
            "ragfs_s3_request_duration_seconds",
            &[("operation", "GetObject")],
        ) else {
            panic!("missing duration histogram");
        };
        assert_eq!((count, sum), (1, 3_000_000));
        assert_eq!(
            value(&snapshot, "ragfs_s3_inflight_requests", &[]),
            Some(RagfsMetricValue::Gauge(2.0))
        );
    }

    #[test]
    fn outcome_classifies_status_codes() {
        let error = OrchestratorError::<()>::response("bad".into());
        assert_eq!(outcome_of(&error, Some(503)), Outcome::ServerError);
        assert_eq!(outcome_of(&error, Some(429)), Outcome::ServerError);
        assert_eq!(outcome_of(&error, Some(404)), Outcome::ClientError);
        assert_eq!(outcome_of(&error, None), Outcome::Network);
        let timeout = OrchestratorError::<()>::timeout("slow".into());
        assert_eq!(outcome_of(&timeout, None), Outcome::Timeout);
    }
}

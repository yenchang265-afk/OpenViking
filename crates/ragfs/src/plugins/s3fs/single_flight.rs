//! Coalesce concurrent identical lookups into one backend call.
//!
//! When many callers miss the metadata cache for the same path at once (a hot
//! file right after its entry expires, or a burst of requests while S3 is
//! slow), only the first issues S3 requests; the rest wait for its outcome.

use std::collections::HashMap;
use std::future::Future;
use std::sync::{Arc, Mutex};

use tokio::sync::watch;

use crate::core::{Error, Result};

type Outcome<T> = std::result::Result<T, Arc<Error>>;
type Receiver<T> = watch::Receiver<Option<Outcome<T>>>;
type Flights<T> = Mutex<HashMap<String, Receiver<T>>>;

/// Per-key de-duplication of in-flight lookups.
pub(crate) struct SingleFlight<T> {
    inflight: Flights<T>,
}

impl<T> Default for SingleFlight<T> {
    fn default() -> Self {
        Self {
            inflight: Mutex::new(HashMap::new()),
        }
    }
}

impl<T: Clone> SingleFlight<T> {
    /// Run `fetch` for `key`, or wait for an identical lookup already running.
    ///
    /// Waiters receive a copy of the leader's result. If the leader is dropped
    /// before finishing (its caller was cancelled), waiters run `fetch` themselves.
    pub(crate) async fn run<F, Fut>(&self, key: &str, fetch: F) -> Result<T>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<T>>,
    {
        let leader = {
            let mut inflight = self.lock();
            match inflight.get(key) {
                Some(rx) => Err(rx.clone()),
                None => {
                    let (tx, rx) = watch::channel(None);
                    inflight.insert(key.to_string(), rx.clone());
                    Ok((tx, rx))
                }
            }
        };

        match leader {
            Ok((tx, rx)) => {
                let _flight = FlightGuard {
                    inflight: &self.inflight,
                    key,
                    rx,
                };
                let result = fetch().await;
                let shared = match &result {
                    Ok(value) => Ok(value.clone()),
                    Err(err) => Err(Arc::new(replicate_error(err))),
                };
                let _ = tx.send(Some(shared));
                result
            }
            Err(mut rx) => match wait_for_leader(&mut rx).await {
                Some(outcome) => outcome.map_err(|err| replicate_error(&err)),
                None => fetch().await,
            },
        }
    }
}

impl<T> SingleFlight<T> {
    /// Detach the in-flight lookup for `key`: later callers start a fresh one.
    ///
    /// Call this when the underlying data changes, so nobody arriving after the
    /// change receives a result fetched before it.
    pub(crate) fn forget(&self, key: &str) {
        self.lock().remove(key);
    }

    /// Detach in-flight lookups for `prefix` and every path below it.
    pub(crate) fn forget_prefix(&self, prefix: &str) {
        let prefix = prefix.trim_end_matches('/');
        let child_prefix = format!("{prefix}/");
        self.lock()
            .retain(|key, _| key != prefix && !key.starts_with(&child_prefix));
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, Receiver<T>>> {
        self.inflight.lock().unwrap_or_else(|e| e.into_inner())
    }
}

/// The leader's outcome, or `None` if it was dropped without producing one.
async fn wait_for_leader<T: Clone>(rx: &mut Receiver<T>) -> Option<Outcome<T>> {
    loop {
        if let Some(outcome) = rx.borrow_and_update().clone() {
            return Some(outcome);
        }
        if rx.changed().await.is_err() {
            return rx.borrow().clone();
        }
    }
}

/// Removes the leader's in-flight entry when it finishes or is cancelled.
struct FlightGuard<'a, T> {
    inflight: &'a Flights<T>,
    key: &'a str,
    /// Identifies this flight: after `forget`, a newer flight may own `key`.
    rx: Receiver<T>,
}

impl<T> Drop for FlightGuard<'_, T> {
    fn drop(&mut self) {
        let mut inflight = self.inflight.lock().unwrap_or_else(|e| e.into_inner());
        if inflight
            .get(self.key)
            .is_some_and(|current| current.same_channel(&self.rx))
        {
            inflight.remove(self.key);
        }
    }
}

/// `Error` is not `Clone`; rebuild the variants a metadata lookup can produce.
fn replicate_error(err: &Error) -> Error {
    match err {
        Error::NotFound(msg) => Error::NotFound(msg.clone()),
        Error::Timeout(msg) => Error::Timeout(msg.clone()),
        Error::Network(msg) => Error::Network(msg.clone()),
        Error::PermissionDenied(msg) => Error::PermissionDenied(msg.clone()),
        Error::Config(msg) => Error::Config(msg.clone()),
        Error::Internal(msg) => Error::Internal(msg.clone()),
        other => Error::internal(other.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;

    async fn slow_lookup(calls: &AtomicUsize, result: Result<u32>) -> Result<u32> {
        calls.fetch_add(1, Ordering::SeqCst);
        tokio::time::sleep(Duration::from_millis(50)).await;
        result
    }

    #[tokio::test]
    async fn concurrent_callers_share_one_fetch() {
        let flights = SingleFlight::default();
        let calls = AtomicUsize::new(0);

        let results = futures::future::join_all(
            (0..10).map(|_| flights.run("k", || slow_lookup(&calls, Ok(7)))),
        )
        .await;

        assert!(results.iter().all(|r| matches!(r, Ok(7))));
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn waiters_receive_the_leaders_error_kind() {
        let flights = SingleFlight::<u32>::default();
        let calls = AtomicUsize::new(0);

        let results = futures::future::join_all(
            (0..3)
                .map(|_| flights.run("k", || slow_lookup(&calls, Err(Error::timeout("slow s3"))))),
        )
        .await;

        assert!(results
            .iter()
            .all(|r| matches!(r, Err(Error::Timeout(msg)) if msg == "slow s3")));
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn callers_after_forget_start_a_fresh_lookup() {
        let flights = SingleFlight::default();
        let calls = AtomicUsize::new(0);

        let before = flights.run("/a/b", || slow_lookup(&calls, Ok(1)));
        let after = async {
            // Let the first lookup start, then simulate a write to the path.
            tokio::time::sleep(Duration::from_millis(10)).await;
            flights.forget_prefix("/a");
            flights.run("/a/b", || slow_lookup(&calls, Ok(2))).await
        };
        let (before, after) = tokio::join!(before, after);

        assert!(matches!((before, after), (Ok(1), Ok(2))));
        assert_eq!(calls.load(Ordering::SeqCst), 2);
        // The first leader finished last-but-one and must not remove the
        // second flight's entry (both are gone once both complete).
        assert!(flights.inflight.lock().unwrap().is_empty());
    }

    #[test]
    fn forget_prefix_spares_siblings() {
        let flights = SingleFlight::<u32>::default();
        for key in ["/a", "/a/b", "/ab", "/c"] {
            let (_tx, rx) = watch::channel(None);
            flights.inflight.lock().unwrap().insert(key.to_string(), rx);
        }

        flights.forget_prefix("/a/");

        let mut left: Vec<String> = flights.inflight.lock().unwrap().keys().cloned().collect();
        left.sort();
        assert_eq!(left, ["/ab", "/c"]);
    }

    #[tokio::test]
    async fn different_keys_do_not_coalesce() {
        let flights = SingleFlight::default();
        let calls = AtomicUsize::new(0);

        let (a, b) = tokio::join!(
            flights.run("a", || slow_lookup(&calls, Ok(1))),
            flights.run("b", || slow_lookup(&calls, Ok(2))),
        );

        assert!(matches!((a, b), (Ok(1), Ok(2))));
        assert_eq!(calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn waiter_fetches_itself_when_leader_is_cancelled() {
        let flights = SingleFlight::default();
        let calls = AtomicUsize::new(0);

        let leader = flights.run("k", || async {
            calls.fetch_add(1, Ordering::SeqCst);
            std::future::pending::<Result<u32>>().await
        });
        let waiter = flights.run("k", || slow_lookup(&calls, Ok(9)));

        // The leader registers first and never finishes; it is dropped after
        // 20ms while the waiter is already waiting on it.
        let cancel_leader = async {
            tokio::select! {
                _ = leader => unreachable!("leader never finishes"),
                _ = tokio::time::sleep(Duration::from_millis(20)) => {}
            }
        };
        let ((), value) = tokio::time::timeout(Duration::from_secs(1), async {
            tokio::join!(cancel_leader, waiter)
        })
        .await
        .expect("waiter hung after leader cancellation");

        assert!(matches!(value, Ok(9)));
        assert_eq!(calls.load(Ordering::SeqCst), 2);
        assert!(flights.inflight.lock().unwrap().is_empty());
    }
}

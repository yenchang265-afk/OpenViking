{{/*
Render ov.conf as pretty JSON. Call with (dict "root" $ "component" "").

component "api" forces off the background jobs that would otherwise run once
per replica (WatchScheduler, session auto-commit) and turns on the account
store watch so API replicas see users added through the control pod. The
"control" component and single-instance mode use .Values.config as given.
*/}}
{{- define "openviking.renderConfig" -}}
{{- $root := .root -}}
{{- $config := deepCopy $root.Values.config -}}
{{- if $root.Values.gateway.enabled }}
{{- $gateway := dict "enabled" true "host" "0.0.0.0" "port" $root.Values.gateway.port "workers" $root.Values.gateway.workers "url" (printf "http://127.0.0.1:%v" $root.Values.gateway.port) "openviking_url" (printf "http://127.0.0.1:%v" ($root.Values.config.server.port | default 1933)) "storage_path" (printf "%s/gateway" $root.Values.persistence.mountPath) }}
{{- $_ := set $config "gateway" (mergeOverwrite $gateway ($config.gateway | default dict)) }}
{{- end }}
{{- if empty $config.storage.workspace }}
{{- $_ := set $config.storage "workspace" (printf "%s/openviking_workspace" (trimSuffix "/" $root.Values.persistence.mountPath)) }}
{{- end }}
{{- if eq .component "api" }}
{{- $_ := set $config "enable_watch_scheduler" false }}
{{- $memory := $config.memory | default dict }}
{{- $autoCommit := $memory.session_auto_commit | default dict }}
{{- $_ := set $autoCommit "enabled" false }}
{{- $_ := set $memory "session_auto_commit" $autoCommit }}
{{- $_ := set $config "memory" $memory }}
{{- if not (hasKey $config.server "api_key_watch_enabled") }}
{{- $_ := set $config.server "api_key_watch_enabled" true }}
{{- end }}
{{- end }}
{{- $config | toPrettyJson }}
{{- end }}

{{/*
Fail fast when multi-instance mode is combined with storage that one pod
owns. Every check mirrors a per-process limit in the server.
*/}}
{{- define "openviking.validateMultiInstance" -}}
{{- $config := .Values.config -}}
{{- $storage := $config.storage | default dict -}}
{{- $vectordb := $storage.vectordb | default dict -}}
{{- $agfs := $storage.agfs | default dict -}}
{{- $queuefs := $agfs.queuefs | default dict -}}
{{- $pathlock := $agfs.pathlock | default dict -}}
{{- $cachefs := $agfs.cachefs | default dict -}}
{{- $server := $config.server | default dict -}}
{{- $tempUpload := $server.temp_upload | default dict -}}
{{- $vectorBackend := $vectordb.backend | default "local" -}}
{{- if has $vectorBackend (list "local" "cuvs") }}
{{- fail (printf "multiInstance.enabled requires a remote vector backend (elasticsearch, opengauss or http); config.storage.vectordb.backend=%q is embedded and locks the workspace to one process." $vectorBackend) }}
{{- end }}
{{- if ne ($agfs.backend | default "local") "s3" }}
{{- fail "multiInstance.enabled requires config.storage.agfs.backend=\"s3\" so every replica sees the same files." }}
{{- end }}
{{- if ne (($config.cache | default dict).provider | default "") "redis" }}
{{- fail "multiInstance.enabled requires config.cache.provider=\"redis\" for queues and path locks." }}
{{- end }}
{{- if ne ($queuefs.backend | default "sqlite") "cache" }}
{{- fail "multiInstance.enabled requires config.storage.agfs.queuefs.backend=\"cache\"; a SQLite queue on a pod's emptyDir loses queued jobs when the pod goes away." }}
{{- end }}
{{- if ne ($pathlock.provider | default "filesystem") "cache" }}
{{- fail "multiInstance.enabled requires config.storage.agfs.pathlock.provider=\"cache\" so path locks hold across pods." }}
{{- end }}
{{- if empty $pathlock.namespace }}
{{- fail "multiInstance.enabled requires config.storage.agfs.pathlock.namespace; every pod must use the same value." }}
{{- end }}
{{- if eq ($cachefs.backend | default "local") "cache" }}
{{- fail "config.storage.agfs.cachefs.backend=\"cache\" assumes a single writer per namespace; use \"local\" with multiInstance.enabled." }}
{{- end }}
{{- if ne ($tempUpload.default_mode | default "local") "shared" }}
{{- fail "multiInstance.enabled requires config.server.temp_upload.default_mode=\"shared\" so any replica can finish an upload." }}
{{- end }}
{{- if .Values.gateway.enabled }}
{{- fail "gateway.enabled is not supported with multiInstance.enabled; the gateway's storage must stay on one host. Deploy it as a separate single-replica release." }}
{{- end }}
{{- end }}

{{/*
Expand the name of the chart.
*/}}
{{- define "openviking.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this
(by the DNS naming spec). If release name contains chart name it will be used
as a full name.
*/}}
{{- define "openviking.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "openviking.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "openviking.labels" -}}
helm.sh/chart: {{ include "openviking.chart" . }}
{{ include "openviking.selectorLabels" . }}
{{- $appVersion := include "openviking.appVersion" . }}
{{- if $appVersion }}
app.kubernetes.io/version: {{ $appVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "openviking.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openviking.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Selector labels for the single-replica watch scheduler Deployment. A different
app name keeps its pods out of the API Deployment and the Service.
*/}}
{{- define "openviking.schedulerSelectorLabels" -}}
app.kubernetes.io/name: {{ printf "%s-scheduler" (include "openviking.name" .) | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Fail early on settings that cannot work with several replicas.
*/}}
{{- define "openviking.validateMultiInstance" -}}
{{- $mi := .Values.multiInstance.enabled }}
{{- if and (gt (int .Values.replicaCount) 1) (not $mi) }}
{{- fail "replicaCount > 1 requires multiInstance.enabled=true and shared backends (see \"Multiple replicas\" in deploy/helm/README.md)." }}
{{- end }}
{{- if $mi }}
{{- $c := .Values.config | default dict }}
{{- $storage := $c.storage | default dict }}
{{- $agfs := $storage.agfs | default dict }}
{{- $vectordb := $storage.vectordb | default dict }}
{{- if has ($vectordb.backend | default "local") (list "local" "cuvs") }}
{{- fail "multiInstance requires a remote vector store (config.storage.vectordb.backend: elasticsearch, http or opengauss); the embedded local/cuvs store locks the workspace to one process." }}
{{- end }}
{{- if eq ($agfs.backend | default "local") "local" }}
{{- fail "multiInstance requires shared file storage (config.storage.agfs.backend: s3); local AGFS gives each pod its own files." }}
{{- end }}
{{- if not (($c.cache | default dict).provider) }}
{{- fail "multiInstance requires a shared cache provider (config.cache.provider: redis) for PathLock, CacheFS and QueueFS." }}
{{- end }}
{{- if ne (($agfs.pathlock | default dict).provider | default "filesystem") "cache" }}
{{- fail "multiInstance requires config.storage.agfs.pathlock.provider: cache so path locks are shared between pods." }}
{{- end }}
{{- if ne (($storage.task_store | default dict).provider | default "file") "mysql" }}
{{- fail "multiInstance requires config.storage.task_store.provider: mysql; the file Task store counts open work in process memory, so a Task whose work another pod finishes waits forever." }}
{{- end }}
{{- if .Values.gateway.enabled }}
{{- fail "multiInstance does not support gateway.enabled: the gateway's SQLite databases serve one pod only." }}
{{- end }}
{{- if (($c.oauth | default dict).enabled) }}
{{- fail "multiInstance does not support config.oauth.enabled: OAuth tokens are stored in each pod's workspace SQLite." }}
{{- end }}
{{- if .Values.bot.enabled }}
{{- fail "multiInstance does not support bot.enabled: vikingbot keeps its state in the pod's workspace." }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Deployment strategy: explicit .Values.strategy, else Recreate for one replica
and a surge-only RollingUpdate in multiInstance mode.
*/}}
{{- define "openviking.strategy" -}}
{{- if .Values.strategy }}
{{- toYaml .Values.strategy }}
{{- else if .Values.multiInstance.enabled }}
type: RollingUpdate
rollingUpdate:
  maxSurge: 1
  maxUnavailable: 0
{{- else }}
type: Recreate
{{- end }}
{{- end }}

{{/*
Pod template shared by the API and scheduler Deployments.
Call with (dict "root" $ "scheduler" true|false).
*/}}
{{- define "openviking.podTemplate" -}}
{{- $root := .root }}
{{- $v := $root.Values }}
{{- $mi := $v.multiInstance.enabled }}
metadata:
  annotations:
    checksum/config: {{ include (print $root.Template.BasePath "/configmap.yaml") $root | sha256sum }}
    {{- with $v.podAnnotations }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  labels:
    {{- if .scheduler }}
    {{- include "openviking.schedulerSelectorLabels" $root | nindent 4 }}
    app.kubernetes.io/component: scheduler
    {{- else }}
    {{- include "openviking.labels" $root | nindent 4 }}
    {{- if $mi }}
    app.kubernetes.io/component: api
    {{- end }}
    {{- end }}
    {{- with $v.podLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  {{- with $v.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- if or $v.serviceAccount.create $v.serviceAccount.name }}
  serviceAccountName: {{ include "openviking.serviceAccountName" $root }}
  {{- end }}
  {{- with $v.podSecurityContext }}
  securityContext:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  containers:
    - name: {{ $root.Chart.Name }}
      {{- with $v.securityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      image: {{ include "openviking.image" $root | quote }}
      imagePullPolicy: {{ $v.image.pullPolicy }}
      env:
        {{- if and $v.gateway.enabled $v.gateway.existingSecret }}
        - name: OPENVIKING_GATEWAY_MANAGEMENT_KEY
          valueFrom:
            secretKeyRef:
              name: {{ $v.gateway.existingSecret }}
              key: management-key
              optional: true
        - name: OPENVIKING_GATEWAY_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: {{ $v.gateway.existingSecret }}
              key: encryption-key
              optional: true
        {{- end }}
        - name: OPENVIKING_CONFIG_FILE
          value: {{ printf "%s/ov.conf" $v.persistence.mountPath | quote }}
        - name: OPENVIKING_CLI_CONFIG_FILE
          value: {{ printf "%s/ovcli.conf" $v.persistence.mountPath | quote }}
        - name: OPENVIKING_WITH_BOT
          value: {{ ternary "1" "0" $v.bot.enabled | quote }}
        {{- if $mi }}
        - name: OV_INSTANCE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: OV_ENABLE_WATCH_SCHEDULER
          value: {{ ternary "true" "false" (and .scheduler true) | quote }}
        {{- end }}
        {{- with $v.extraEnv }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      {{- with $v.envFrom }}
      envFrom:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      ports:
        - name: http
          containerPort: {{ $v.config.server.port | default 1933 }}
          protocol: TCP
      {{- with $v.livenessProbe }}
      livenessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $v.readinessProbe }}
      readinessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- $resources := $v.resources }}
      {{- if and .scheduler $v.multiInstance.scheduler.resources }}
      {{- $resources = $v.multiInstance.scheduler.resources }}
      {{- end }}
      {{- with $resources }}
      resources:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      volumeMounts:
        - name: data
          mountPath: {{ $v.persistence.mountPath }}
        - name: config
          mountPath: {{ printf "%s/ov.conf" $v.persistence.mountPath | quote }}
          subPath: ov.conf
          readOnly: true
  volumes:
    - name: config
      configMap:
        name: {{ include "openviking.fullname" $root }}-config
    - name: data
      {{- if $mi }}
      emptyDir:
        {{- if $v.multiInstance.workspaceSizeLimit }}
        sizeLimit: {{ $v.multiInstance.workspaceSizeLimit }}
        {{- else }} {}
        {{- end }}
      {{- else if $v.persistence.enabled }}
      persistentVolumeClaim:
        claimName: {{ $v.persistence.existingClaim | default (printf "%s-data" (include "openviking.fullname" $root)) }}
      {{- else }}
      emptyDir: {}
      {{- end }}
  {{- with $v.nodeSelector }}
  nodeSelector:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $v.affinity }}
  affinity:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $v.tolerations }}
  tolerations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}

{{/*
Create the name of the service account to use.
*/}}
{{- define "openviking.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "openviking.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the deployed app version label.
*/}}
{{- define "openviking.appVersion" -}}
{{- default "latest" .Values.image.tag -}}
{{- end }}

{{/*
Return the image name including tag.
*/}}
{{- define "openviking.image" -}}
{{- $tag := default "latest" .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end }}

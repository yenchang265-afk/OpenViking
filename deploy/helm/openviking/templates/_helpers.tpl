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

{{/*
Studio Deployment and Service name.
*/}}
{{- define "openviking.studio.fullname" -}}
{{- printf "%s-studio" (include "openviking.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Studio selector labels. The name differs from the server's so the server
Service and Deployment selectors (name + instance) never match Studio pods.
*/}}
{{- define "openviking.studio.selectorLabels" -}}
app.kubernetes.io/name: {{ printf "%s-studio" (include "openviking.name" .) | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: studio
{{- end }}

{{/*
Studio common labels.
*/}}
{{- define "openviking.studio.labels" -}}
helm.sh/chart: {{ include "openviking.chart" . }}
{{ include "openviking.studio.selectorLabels" . }}
app.kubernetes.io/version: {{ default "latest" .Values.studio.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Return the Studio image name including tag.
*/}}
{{- define "openviking.studio.image" -}}
{{- $repository := required "studio.image.repository is required when studio.enabled=true (an image built with `docker build --target studio`)" .Values.studio.image.repository -}}
{{- printf "%s:%s" $repository (default "latest" .Values.studio.image.tag) -}}
{{- end }}

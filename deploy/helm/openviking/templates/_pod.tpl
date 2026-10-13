{{/*
Labels for a multi-instance component (api or control).
Call with (dict "root" $ "component" "api").
*/}}
{{- define "openviking.componentLabels" -}}
{{ include "openviking.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "openviking.componentSelectorLabels" -}}
{{ include "openviking.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Pod template shared by the single-instance Deployment and the multi-instance
api/control Deployments. Call with (dict "root" $ "component" "") for single
instance, or "api" / "control" in multi-instance mode.
*/}}
{{- define "openviking.podTemplate" -}}
{{- $root := .root -}}
{{- $component := .component -}}
{{- $multi := $root.Values.multiInstance.enabled -}}
{{- $mountPath := $root.Values.persistence.mountPath -}}
{{- $resources := $root.Values.resources -}}
{{- if $multi }}
{{- $resources = (index $root.Values.multiInstance $component).resources | default $root.Values.resources -}}
{{- end -}}
metadata:
  annotations:
    {{- if $multi }}
    checksum/config: {{ include "openviking.renderConfig" (dict "root" $root "component" $component) | sha256sum }}
    {{- else }}
    checksum/config: {{ include (print $root.Template.BasePath "/configmap.yaml") $root | sha256sum }}
    {{- end }}
    {{- with $root.Values.podAnnotations }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  labels:
    {{- if $multi }}
    {{- include "openviking.componentLabels" (dict "root" $root "component" $component) | nindent 4 }}
    {{- else }}
    {{- include "openviking.labels" $root | nindent 4 }}
    {{- end }}
    {{- with $root.Values.podLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  {{- with $root.Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- if or $root.Values.serviceAccount.create $root.Values.serviceAccount.name }}
  serviceAccountName: {{ include "openviking.serviceAccountName" $root }}
  {{- end }}
  {{- with $root.Values.podSecurityContext }}
  securityContext:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- if $multi }}
  terminationGracePeriodSeconds: {{ $root.Values.multiInstance.terminationGracePeriodSeconds }}
  {{- end }}
  containers:
    - name: {{ $root.Chart.Name }}
      {{- with $root.Values.securityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      image: {{ include "openviking.image" $root | quote }}
      imagePullPolicy: {{ $root.Values.image.pullPolicy }}
      env:
        {{- if $root.Values.gateway.enabled }}
        - name: OPENVIKING_GATEWAY_ADMIN_TOKEN
          valueFrom:
            secretKeyRef:
              name: {{ required "gateway.existingSecret is required" $root.Values.gateway.existingSecret }}
              key: admin-token
        {{- end }}
        - name: OPENVIKING_CONFIG_FILE
          value: {{ printf "%s/ov.conf" $mountPath | quote }}
        - name: OPENVIKING_CLI_CONFIG_FILE
          value: {{ printf "%s/ovcli.conf" $mountPath | quote }}
        - name: OPENVIKING_WITH_BOT
          value: {{ ternary "1" "0" $root.Values.bot.enabled | quote }}
        {{- with $root.Values.extraEnv }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      ports:
        - name: http
          containerPort: {{ $root.Values.config.server.port | default 1933 }}
          protocol: TCP
      {{- if and $multi (gt (int $root.Values.multiInstance.preStopSleepSeconds) 0) }}
      lifecycle:
        preStop:
          exec:
            command: ["sleep", {{ $root.Values.multiInstance.preStopSleepSeconds | toString | quote }}]
      {{- end }}
      {{- with $root.Values.livenessProbe }}
      livenessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $root.Values.readinessProbe }}
      readinessProbe:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $resources }}
      resources:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      volumeMounts:
        - name: data
          mountPath: {{ $mountPath }}
        - name: config
          mountPath: {{ printf "%s/ov.conf" $mountPath | quote }}
          subPath: ov.conf
          readOnly: true
    {{- if $root.Values.gateway.enabled }}
    - name: gateway
      image: {{ include "openviking.image" $root | quote }}
      imagePullPolicy: {{ $root.Values.image.pullPolicy }}
      command: ["openviking-gateway"]
      args: ["--config", {{ printf "%s/ov.conf" $mountPath | quote }}]
      env:
        - name: OPENVIKING_GATEWAY_ADMIN_TOKEN
          valueFrom:
            secretKeyRef:
              name: {{ $root.Values.gateway.existingSecret }}
              key: admin-token
        - name: OPENVIKING_GATEWAY_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: {{ $root.Values.gateway.existingSecret }}
              key: encryption-key
      ports:
        - name: gateway
          containerPort: {{ $root.Values.gateway.port }}
      readinessProbe:
        httpGet:
          path: /health
          port: gateway
      resources:
        {{- toYaml $root.Values.gateway.resources | nindent 8 }}
      volumeMounts:
        - name: data
          mountPath: {{ $mountPath }}
        - name: config
          mountPath: {{ printf "%s/ov.conf" $mountPath | quote }}
          subPath: ov.conf
          readOnly: true
    {{- end }}
  volumes:
    - name: config
      configMap:
        {{- if $multi }}
        name: {{ include "openviking.fullname" $root }}-{{ $component }}-config
        {{- else }}
        name: {{ include "openviking.fullname" $root }}-config
        {{- end }}
    - name: data
      {{- if $multi }}
      emptyDir:
        {{- with $root.Values.multiInstance.localVolumeSizeLimit }}
        sizeLimit: {{ . }}
        {{- end }}
      {{- else if $root.Values.persistence.enabled }}
      persistentVolumeClaim:
        claimName: {{ $root.Values.persistence.existingClaim | default (printf "%s-data" (include "openviking.fullname" $root)) }}
      {{- else }}
      emptyDir: {}
      {{- end }}
  {{- with $root.Values.nodeSelector }}
  nodeSelector:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $root.Values.affinity }}
  affinity:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with $root.Values.tolerations }}
  tolerations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- if and $multi (eq $component "api") $root.Values.multiInstance.api.topologySpread.enabled }}
  topologySpreadConstraints:
    {{- range list "kubernetes.io/hostname" "topology.kubernetes.io/zone" }}
    - maxSkew: 1
      topologyKey: {{ . }}
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          {{- include "openviking.componentSelectorLabels" (dict "root" $root "component" "api") | nindent 10 }}
    {{- end }}
  {{- end }}
{{- end }}

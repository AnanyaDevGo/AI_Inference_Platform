{{/*
Expand the name of the chart.
*/}}
{{- define "infervoyage.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "infervoyage.fullname" -}}
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
{{- define "infervoyage.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "infervoyage.labels" -}}
helm.sh/chart: {{ include "infervoyage.chart" . }}
{{ include "infervoyage.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "infervoyage.selectorLabels" -}}
app.kubernetes.io/name: {{ include "infervoyage.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create component names
*/}}
{{- define "infervoyage.postgres.fullname" -}}
{{- printf "%s-postgres" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "infervoyage.redis.fullname" -}}
{{- printf "%s-redis" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "infervoyage.ollama.fullname" -}}
{{- printf "%s-ollama" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "infervoyage.api.fullname" -}}
{{- printf "%s-api" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "infervoyage.frontend.fullname" -}}
{{- printf "%s-frontend" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "infervoyage.locust.fullname" -}}
{{- printf "%s-locust" (include "infervoyage.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

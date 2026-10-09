{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "mukthiguru.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "mukthiguru.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mukthiguru.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mukthiguru.labels" -}}
helm.sh/chart: {{ include "mukthiguru.chart" . }}
{{ include "mukthiguru.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mukthiguru.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mukthiguru.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend fullname
*/}}
{{- define "mukthiguru.backend.fullname" -}}
{{- printf "%s-backend" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Frontend fullname
*/}}
{{- define "mukthiguru.frontend.fullname" -}}
{{- printf "%s-frontend" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Redis fullname
*/}}
{{- define "mukthiguru.redis.fullname" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis-master" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-redis" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Qdrant fullname
*/}}
{{- define "mukthiguru.qdrant.fullname" -}}
{{- printf "%s-qdrant" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Neo4j fullname
*/}}
{{- define "mukthiguru.neo4j.fullname" -}}
{{- printf "%s-neo4j" (include "mukthiguru.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Redis password
*/}}
{{- define "mukthiguru.redis.password" -}}
{{- if .Values.redis.auth.password -}}
{{- .Values.redis.auth.password -}}
{{- else -}}
{{- randAlphaNum 32 -}}
{{- end -}}
{{- end }}
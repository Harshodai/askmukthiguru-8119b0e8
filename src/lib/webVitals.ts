/**
 * Web Vitals -> Sentry reporter.
 *
 * Ships Core Web Vitals (LCP, INP, CLS, FCP, TTFB) as Sentry breadcrumbs +
 * one summary event per navigation so slow pages surface with their
 * network/device fingerprint attached.
 */
import { onCLS, onFCP, onINP, onLCP, onTTFB, type Metric } from "web-vitals";
import * as Sentry from "@sentry/react";

type NetInfo = { effectiveType?: string; downlink?: number; rtt?: number; saveData?: boolean };

function connection(): NetInfo {
  const c = (navigator as unknown as { connection?: NetInfo }).connection;
  return c ?? {};
}

function deviceContext() {
  const nav = navigator as unknown as { deviceMemory?: number; hardwareConcurrency?: number };
  return {
    deviceMemory: nav.deviceMemory,
    hardwareConcurrency: nav.hardwareConcurrency,
    ...connection(),
  };
}

const THRESHOLDS: Record<string, { good: number; poor: number }> = {
  LCP: { good: 2500, poor: 4000 },
  INP: { good: 200, poor: 500 },
  CLS: { good: 0.1, poor: 0.25 },
  FCP: { good: 1800, poor: 3000 },
  TTFB: { good: 800, poor: 1800 },
};

function rating(name: string, value: number): "good" | "needs-improvement" | "poor" {
  const t = THRESHOLDS[name];
  if (!t) return "good";
  if (value <= t.good) return "good";
  if (value <= t.poor) return "needs-improvement";
  return "poor";
}

function report(metric: Metric) {
  const r = rating(metric.name, metric.value);
  const route = typeof window !== "undefined" ? window.location.pathname : "unknown";

  Sentry.addBreadcrumb({
    category: "web-vital",
    level: r === "poor" ? "warning" : "info",
    message: `${metric.name}=${Math.round(metric.value)} (${r})`,
    data: { ...metric, route, ...deviceContext() },
  });

  // Only escalate poor metrics to Sentry as events to avoid noise.
  if (r === "poor") {
    Sentry.captureMessage(`webvital.poor.${metric.name}`, {
      level: "warning",
      tags: { route, metric: metric.name, rating: r },
      extra: { value: metric.value, id: metric.id, ...deviceContext() },
    });
  }
}

export function initWebVitals() {
  if (typeof window === "undefined") return;
  try {
    onLCP(report);
    onINP(report);
    onCLS(report);
    onFCP(report);
    onTTFB(report);
  } catch (err) {
    console.warn("[webVitals] init failed", err);
  }
}

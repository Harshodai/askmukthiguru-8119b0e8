"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  monthKey,
  isFirstMondayUtc,
  findExistingMonthlyIssue,
} = require("./monthly_backup_reminder");

test("scheduled reminder runs only on the first Monday in UTC", () => {
  assert.equal(isFirstMondayUtc(new Date("2026-11-02T09:00:00.000Z")), true);
  assert.equal(isFirstMondayUtc(new Date("2026-11-09T09:00:00.000Z")), false);
  assert.equal(isFirstMondayUtc(new Date("2026-11-01T09:00:00.000Z")), false);
  assert.equal(isFirstMondayUtc(new Date("2026-12-07T09:00:00.000Z")), true);
});

test("month key is stable and based on UTC", () => {
  assert.equal(monthKey(new Date("2026-11-30T23:59:59.000Z")), "2026-11");
  assert.equal(monthKey(new Date("2026-12-01T00:00:00.000Z")), "2026-12");
});

test("old date-suffixed issues and new month-suffixed issues deduplicate", () => {
  const issues = [
    { number: 100, title: "[OPS] Monthly backup/restore drill — 2026-11-16" },
    { number: 101, title: "[OPS] Monthly backup/restore drill — 2026-11" },
    { number: 102, title: "Unrelated issue" },
    { number: 103, title: "[OPS] Monthly backup/restore drill — 2026-10-26" },
  ];

  const november = findExistingMonthlyIssue(issues, new Date("2026-11-26T12:00:00.000Z"));
  assert.equal(november.number, 100);

  const december = findExistingMonthlyIssue(issues, new Date("2026-12-07T09:00:00.000Z"));
  assert.equal(december, null);
});

test("pull requests are not mistaken for monthly drill issues", () => {
  const issues = [
    { number: 55, title: "[OPS] Monthly backup/restore drill — 2026-11", pull_request: {} },
  ];
  assert.equal(findExistingMonthlyIssue(issues, new Date("2026-11-26T12:00:00.000Z")), null);
});

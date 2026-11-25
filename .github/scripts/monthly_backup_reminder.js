"use strict";

const MONTHLY_ISSUE_PREFIX = "Monthly backup/restore drill";

function monthKey(date) {
  return date.toISOString().slice(0, 7);
}

function isFirstMondayUtc(date) {
  return date.getUTCDay() === 1 && date.getUTCDate() <= 7;
}

function findExistingMonthlyIssue(issues, date) {
  const targetMonth = monthKey(date);
  const titlePattern = /Monthly backup\/restore drill\s+—\s+(\d{4}-\d{2})(?:-\d{2})?/i;

  return issues.find((issue) => {
    if (issue.pull_request || typeof issue.title !== "string") return false;
    const match = issue.title.match(titlePattern);
    return match?.[1] === targetMonth;
  }) || null;
}

module.exports = {
  MONTHLY_ISSUE_PREFIX,
  monthKey,
  isFirstMondayUtc,
  findExistingMonthlyIssue,
};

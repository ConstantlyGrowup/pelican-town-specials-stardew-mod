import type { components } from "../../api/generated/schema";
import { PRODUCT_COPY } from "../../i18n/copy";

type ValidationIssue = components["schemas"]["ValidationIssue"];

const copy = PRODUCT_COPY.zh;

function issueText(issue: ValidationIssue): string {
  const label = copy.validationIssueLabels[issue.code as keyof typeof copy.validationIssueLabels];
  return label ?? issue.message;
}

export function ValidationIssues({ issues }: { issues: ValidationIssue[] }) {
  if (issues.length === 0) {
    return null;
  }
  return (
    <ul className="validation-issues" role="alert" aria-label="校验问题">
      {issues.map((issue, index) => (
        <li
          key={index}
          className={`issue issue-${issue.severity.toLowerCase()}`}
        >
          <span className="issue-severity">{issue.severity}</span>
          <span className="issue-message">{issueText(issue)}</span>
          {issue.path ? <code className="issue-path">{issue.path}</code> : null}
        </li>
      ))}
    </ul>
  );
}

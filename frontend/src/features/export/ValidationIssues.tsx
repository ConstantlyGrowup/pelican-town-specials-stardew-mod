import type { components } from "../../api/generated/schema";
import { useCopy } from "../../i18n/locale";
import type { Copy } from "../../i18n/copy";

type ValidationIssue = components["schemas"]["ValidationIssue"];

function issueText(issue: ValidationIssue, copy: Copy): string {
  const label = copy.validationIssueLabels[issue.code as keyof typeof copy.validationIssueLabels];
  return label ?? issue.message;
}

export function ValidationIssues({ issues }: { issues: ValidationIssue[] }) {
  const copy = useCopy();
  if (issues.length === 0) {
    return null;
  }
  return (
    <ul className="validation-issues" role="alert" aria-label={copy.validationIssuesLabel}>
      {issues.map((issue, index) => (
        <li
          key={index}
          className={`issue issue-${issue.severity.toLowerCase()}`}
        >
          <span className="issue-severity">
            {copy.validationSeverityLabels[issue.severity] ?? issue.severity}
          </span>
          <span className="issue-message">{issueText(issue, copy)}</span>
          {issue.path ? <code className="issue-path">{issue.path}</code> : null}
        </li>
      ))}
    </ul>
  );
}

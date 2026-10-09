import json

def generate_markdown():
    with open('audit_results.json', 'r') as f:
        data = json.load(f)

    total_points = data['total_points']
    schema_issues = data['schema_issues']
    rights_cleared_false_count = data['rights_cleared_false_count']
    content_issues = data['content_issues']
    vec_issues = data['vec_issues']
    exact_duplicates = data['exact_duplicates']
    overlaps = data['overlaps']
    speaker_counts = data['speaker_counts']
    low_videos_count = data['low_videos_count']
    question_context_count = data['question_context_count']
    question_context_samples = data['question_context_samples']

    # Analyze schema issues
    missing_fields = []
    invalid_speakers = []
    not_first_person = []
    not_verbatim = []

    for issue in schema_issues:
        if 'missing' in issue:
            missing_fields.append(issue)
        elif 'Invalid speaker' in issue.get('issue', ''):
            invalid_speakers.append(issue)
        elif 'first_person_eligible not True' in issue.get('issue', ''):
            not_first_person.append(issue)
        elif 'is_verbatim not True' in issue.get('issue', ''):
            not_verbatim.append(issue)

    # Calculate score
    score = 100
    if invalid_speakers:
        score -= 20
    if exact_duplicates:
        score -= 10
    if overlaps:
        score -= 10
    if question_context_count == 0:
        score -= 15
    if rights_cleared_false_count > 0:
        score -= 20
    if content_issues:
        score -= 10
    if vec_issues:
        score -= 10

    score = max(0, score)

    with open('docs/FP_QUALITY_AUDIT_2026-10-04.md', 'w') as f:
        f.write("# FP Quality Audit Report (2026-10-04)\n\n")

        f.write("## Executive Summary\n")
        f.write(f"**Overall Quality Score**: {score}/100\n")
        if score < 80:
            f.write("**Recommendation**: DO NOT DEPLOY. Index needs repair.\n\n")
        else:
            f.write("**Recommendation**: Index is good for production.\n\n")

        f.write(f"**Total Points Audited**: {total_points}\n\n")

        f.write("## 1. Payload Schema Completeness\n")
        f.write(f"- Total schema issues found: {len(schema_issues)}\n")
        f.write(f"- Points with missing fields: {len(missing_fields)}\n")
        if missing_fields:
            f.write(f"  - Example: {missing_fields[0]}\n")
        f.write(f"- Points with invalid speaker values (must be 'krishnaji' or 'preethaji'): {len(invalid_speakers)}\n")
        if invalid_speakers:
            f.write(f"  - Note: Many clips use 'Sri Krishnaji' or 'Sri Preethaji' instead of the lowercase keys.\n")
        f.write(f"- Points with `first_person_eligible` != True: {len(not_first_person)}\n")
        f.write(f"- Points with `is_verbatim` != True: {len(not_verbatim)}\n\n")

        f.write("## 2. Content Quality Gates (50 samples)\n")
        f.write(f"- Total issues in sample: {len(content_issues)}\n")
        if content_issues:
            for issue in content_issues:
                f.write(f"  - Point `{issue['id']}`: {issue['issue']}\n")
        f.write("\n")

        f.write("## 3. Rights Clearance Integrity\n")
        f.write(f"- Points with `rights_cleared` False or None: {rights_cleared_false_count}\n\n")

        f.write("## 4. Embedding Dimension Check\n")
        f.write(f"- Vectors checked: 5 samples\n")
        f.write(f"- Vectors failing 1024-dimension check: {len(vec_issues)}\n\n")

        f.write("## 5. Duplicate / Near-Duplicate Detection\n")
        f.write(f"- Exact text duplicates found: {len(exact_duplicates)}\n")
        if exact_duplicates:
             f.write(f"  - Examples: {exact_duplicates[:3]}\n")
        f.write(f"- Overlapping clips (>50% overlap): {len(overlaps)}\n")
        if overlaps:
             f.write(f"  - Examples: {overlaps[:3]}\n")
        f.write("\n")

        f.write("## 6. Teacher Coverage Distribution\n")
        for speaker, count in speaker_counts.items():
            f.write(f"- {speaker}: {count} clips ({count/total_points*100:.1f}%)\n")
        f.write(f"- Videos with suspiciously few clips (< 3): {low_videos_count}\n\n")

        f.write("## 7. Question Context Coverage\n")
        f.write(f"- Clips with non-empty `question_context`: {question_context_count}\n")
        if question_context_count == 0:
            f.write("- **P1 Issue**: Entire index is missing question contexts!\n")
        elif question_context_samples:
            f.write("- Sample contexts:\n")
            for sid, qc in question_context_samples:
                 f.write(f"  - {sid}: {qc}\n")

        f.write("\n## Issues Summary\n")
        f.write("- **P0**: Speaker labels use incorrect capitalization/formatting ('Sri Krishnaji' instead of 'krishnaji').\n")
        f.write("- **P1**: Question context is completely missing from all clips.\n")
        if exact_duplicates:
             f.write("- **P2**: Exact text duplicates exist in the collection.\n")

if __name__ == '__main__':
    generate_markdown()

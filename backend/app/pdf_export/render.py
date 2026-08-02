"""ReportLab PDF renderers for lesson plan, teacher guide, and assessment book."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.app.schemas.assessment import AssessmentQuestion
from backend.app.schemas.tkp import TeacherKnowledgePackage
from backend.app.security.sanitize import sanitize_html


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TKPTitle",
            parent=base["Heading1"],
            fontSize=16,
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "TKPHeading",
            parent=base["Heading2"],
            fontSize=13,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "subhead": ParagraphStyle(
            "TKPSubhead",
            parent=base["Heading3"],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "TKPBody",
            parent=base["BodyText"],
            fontSize=10,
            leading=14,
            spaceAfter=4,
        ),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    safe = sanitize_html(text or "").replace("\n", "<br/>")
    if not safe.strip():
        safe = "—"
    return Paragraph(safe, style)


def _ensure_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _render_lesson_plan(tkp: TeacherKnowledgePackage, path: Path) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story: list[Any] = []
    cls = tkp.classification
    story.append(_p(f"Lesson Plan — {cls.chapter}", styles["title"]))
    story.append(
        _p(
            f"{cls.subject} | {cls.grade} | {cls.topic} | Difficulty: {cls.difficulty}",
            styles["body"],
        )
    )
    story.append(Spacer(1, 8))
    plan = tkp.teaching_plan
    story.append(_p(f"Total periods: {plan.total_periods}", styles["body"]))
    if plan.overall_rationale:
        story.append(_p(plan.overall_rationale, styles["body"]))

    for period in plan.periods:
        story.append(
            _p(
                f"Period {period.period_number}: {period.title} "
                f"({period.duration_minutes} min)",
                styles["heading"],
            )
        )
        if period.objectives:
            story.append(_p("Objectives", styles["subhead"]))
            for obj in period.objectives:
                story.append(_p(f"• {obj}", styles["body"]))
        if period.concepts_covered:
            story.append(
                _p("Concepts: " + ", ".join(period.concepts_covered), styles["body"])
            )
        if period.pacing_rationale:
            story.append(_p(period.pacing_rationale, styles["body"]))

    doc.build(story)


def _render_teacher_guide(tkp: TeacherKnowledgePackage, path: Path) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story: list[Any] = []
    cls = tkp.classification
    story.append(_p(f"Teacher Guide — {cls.chapter}", styles["title"]))
    story.append(_p(f"{cls.subject} | {cls.grade}", styles["body"]))
    story.append(Spacer(1, 8))

    for period in tkp.classroom_content.periods:
        story.append(_p(f"Period {period.period_number}", styles["heading"]))
        if period.entry_ticket:
            story.append(_p("Entry ticket", styles["subhead"]))
            story.append(_p(period.entry_ticket, styles["body"]))
        if period.teacher_script:
            story.append(_p("Teacher script", styles["subhead"]))
            story.append(_p(period.teacher_script, styles["body"]))
        if period.blackboard_notes:
            story.append(_p("Blackboard notes", styles["subhead"]))
            story.append(_p(period.blackboard_notes, styles["body"]))
        for activity in period.classroom_activities:
            story.append(
                _p(
                    f"Activity: {activity.name} ({activity.activity_type})",
                    styles["subhead"],
                )
            )
            story.append(_p(activity.instructions, styles["body"]))
        if period.checkpoint_questions:
            story.append(_p("Checkpoints", styles["subhead"]))
            for q in period.checkpoint_questions:
                story.append(_p(f"• {q}", styles["body"]))
        if period.exit_ticket:
            story.append(_p("Exit ticket", styles["subhead"]))
            story.append(_p(period.exit_ticket, styles["body"]))
        if period.homework:
            story.append(_p("Homework", styles["subhead"]))
            story.append(_p(period.homework, styles["body"]))
        if period.mentor_moment:
            story.append(_p("Mentor moment", styles["subhead"]))
            story.append(_p(period.mentor_moment, styles["body"]))

    if tkp.activities.activities:
        story.append(_p("Additional activities", styles["heading"]))
        for act in tkp.activities.activities:
            story.append(_p(f"{act.name} ({act.activity_type})", styles["subhead"]))
            story.append(_p(act.instructions, styles["body"]))

    if tkp.gap_analysis.gaps:
        story.append(_p("Learning gaps", styles["heading"]))
        for gap in tkp.gap_analysis.gaps:
            story.append(
                _p(f"{gap.misconception} [{gap.severity.value}]", styles["subhead"])
            )
            story.append(_p(f"Diagnostic: {gap.diagnostic_question}", styles["body"]))
            for action in gap.remedial_actions:
                story.append(_p(f"• {action}", styles["body"]))

    doc.build(story)


def _render_assessment_book(tkp: TeacherKnowledgePackage, path: Path) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story: list[Any] = []
    cls = tkp.classification
    story.append(_p(f"Assessment Book — {cls.chapter}", styles["title"]))
    story.append(
        _p(f"Total marks: {tkp.assessments.total_marks}", styles["body"])
    )
    story.append(Spacer(1, 8))

    def _section(title: str, questions: list[AssessmentQuestion]) -> None:
        story.append(_p(title, styles["heading"]))
        if not questions:
            story.append(_p("No questions in this section.", styles["body"]))
            return
        for i, q in enumerate(questions, start=1):
            story.append(
                _p(
                    f"Q{i}. [{q.question_type.value}] ({q.marks} marks) {q.prompt}",
                    styles["body"],
                )
            )
            if q.options:
                for opt in q.options:
                    story.append(_p(f"    ○ {opt}", styles["body"]))
            story.append(_p(f"Answer: {q.answer_key}", styles["body"]))
            if q.rubric:
                story.append(_p(f"Rubric: {q.rubric}", styles["body"]))
            if q.concepts_tested:
                story.append(
                    _p("Concepts: " + ", ".join(q.concepts_tested), styles["body"])
                )

    _section("Formative", tkp.assessments.formative)
    _section("Summative", tkp.assessments.summative)
    doc.build(story)


async def render_all_pdfs(
    tkp: TeacherKnowledgePackage,
    output_dir: str | Path | None = None,
) -> dict[str, str]:
    """Generate lesson-plan, teacher-guide, and assessment-book PDFs.

    Args:
        tkp: Completed Teacher Knowledge Package.
        output_dir: Destination directory. Defaults to ``tmp/pdfs/{job_id}/``
            when ``job_id`` is set, otherwise a fresh temp directory.

    Returns:
        Mapping of artifact name → absolute file path.
    """
    if output_dir is None:
        job_part = str(tkp.job_id) if tkp.job_id else "anon"
        base = Path("tmp") / "pdfs" / job_part
        try:
            output_dir = _ensure_dir(base)
        except OSError:
            output_dir = Path(tempfile.mkdtemp(prefix="tkp_pdfs_"))
    else:
        output_dir = _ensure_dir(Path(output_dir))

    paths = {
        "lesson-plan": output_dir / "lesson-plan.pdf",
        "teacher-guide": output_dir / "teacher-guide.pdf",
        "assessment-book": output_dir / "assessment-book.pdf",
    }

    _render_lesson_plan(tkp, paths["lesson-plan"])
    _render_teacher_guide(tkp, paths["teacher-guide"])
    _render_assessment_book(tkp, paths["assessment-book"])

    return {name: str(path.resolve()) for name, path in paths.items()}

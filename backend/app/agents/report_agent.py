from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.agents.base import AgentResult, adk_agent

ADK_AGENT = adk_agent(
    "report_generation_agent",
    "Build session, engagement, emotion analytics, and PDF reports personalized to the instructor.",
)

# Emotion → human-readable label for reports
EMOTION_LABELS = {
    "happy": "Happy / Engaged",
    "neutral": "Neutral",
    "sad": "Sad / Withdrawn",
    "angry": "Frustrated / Angry",
    "surprise": "Surprised / Alert",
    "fear": "Anxious / Fearful",
    "disgust": "Disengaged / Disgusted",
}


class ReportGenerationAgent:
    name = "Report Generation Agent"

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def build(
        self,
        session_id: int,
        engagement: dict,
        emotions: dict,
        recommendations: dict,
        instructor_name: str = "Instructor",
        session_title: str = "Session",
        has_students: bool = True,
    ) -> AgentResult:
        """
        Build a session report.

        Parameters
        ----------
        session_id      : database session ID
        engagement      : result dict from StudentEngagementAgent.calculate()
        emotions        : result dict from EmotionAnalysisAgent.distributions()
        recommendations : result dict from RecommendationAgent.recommend()
        instructor_name : full name of the instructor running the session
        session_title   : title of the session being reported on
        has_students    : whether any students attended; False → short report
        """
        if not has_students:
            summary = (
                f"No students attended session '{session_title}' yet, "
                f"{instructor_name}. Start the session and invite students "
                "to collect emotion and engagement data."
            )
            pdf_path = self._pdf_no_students(session_id, instructor_name, session_title)
            return AgentResult(
                self.name,
                {
                    "summary": summary,
                    "pdf_path": pdf_path,
                    "has_students": False,
                },
            )

        engagement_pct = engagement.get("engagement_percentage", 0)
        dominant_emotions = recommendations.get("dominant_emotions", [])
        recs = recommendations.get("recommendations", ["Review pacing"])

        # Personalised engagement verdict
        if engagement_pct >= 80:
            verdict = f"Excellent engagement in '{session_title}', {instructor_name}!"
        elif engagement_pct >= 60:
            verdict = (
                f"Moderate engagement in '{session_title}', {instructor_name}. "
                "A few improvements are recommended below."
            )
        else:
            verdict = (
                f"Low engagement detected in '{session_title}', {instructor_name}. "
                "Immediate instructional adjustments are advised."
            )

        # Human-readable dominant emotions
        emotion_labels = [EMOTION_LABELS.get(e, e.capitalize()) for e in dominant_emotions]

        summary = (
            f"{verdict} "
            f"Overall engagement: {engagement_pct}%. "
            f"Dominant emotions observed: {', '.join(emotion_labels) if emotion_labels else 'None recorded'}. "
            f"Top recommendation: {recs[0]}."
        )

        pdf_path = self._pdf(
            session_id,
            instructor_name,
            session_title,
            engagement_pct,
            emotion_labels,
            recs,
        )
        return AgentResult(
            self.name,
            {
                "summary": summary,
                "pdf_path": pdf_path,
                "has_students": True,
            },
        )

    # ------------------------------------------------------------------ #
    #  PDF builders                                                        #
    # ------------------------------------------------------------------ #

    def _pdf(
        self,
        session_id: int,
        instructor_name: str,
        session_title: str,
        engagement_pct: float,
        emotion_labels: list[str],
        recommendations: list[str],
    ) -> str:
        path = self._out_path(session_id)
        c = canvas.Canvas(str(path), pagesize=letter)
        c.setTitle("EduSense Session Report")

        y = 740
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, y, "EduSense Session Report")
        y -= 28

        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"Session: {session_title}")
        y -= 18
        c.drawString(72, y, f"Instructor: {instructor_name}")
        y -= 30

        c.setFont("Helvetica-Bold", 13)
        c.drawString(72, y, f"Overall Engagement: {engagement_pct}%")
        y -= 24

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Dominant Emotions Observed:")
        y -= 18
        c.setFont("Helvetica", 11)
        for label in (emotion_labels or ["No data"]):
            c.drawString(90, y, f"• {label}")
            y -= 16
        y -= 10

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Recommendations:")
        y -= 18
        c.setFont("Helvetica", 11)
        for item in recommendations:
            c.drawString(90, y, f"- {item[:90]}")
            y -= 16
            if y < 80:
                c.showPage()
                y = 740

        c.save()
        return str(path)

    def _pdf_no_students(
        self, session_id: int, instructor_name: str, session_title: str
    ) -> str:
        path = self._out_path(session_id)
        c = canvas.Canvas(str(path), pagesize=letter)
        c.setTitle("EduSense Session Report")
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, 740, "EduSense Session Report")
        c.setFont("Helvetica", 11)
        c.drawString(72, 710, f"Session: {session_title}")
        c.drawString(72, 690, f"Instructor: {instructor_name}")
        c.setFont("Helvetica-Bold", 13)
        c.drawString(72, 655, "No student attended yet.")
        c.setFont("Helvetica", 11)
        c.drawString(72, 630, "Start the session and invite students to begin collecting data.")
        c.save()
        return str(path)

    @staticmethod
    def _out_path(session_id: int) -> Path:
        out_dir = Path(__file__).resolve().parents[2] / "static" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"session-{session_id}-report.pdf"

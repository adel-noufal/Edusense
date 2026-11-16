"""
Migration script to fix existing exams with fullscreen_lock=False.
For any quiz where is_exam=True but fullscreen_lock=False, set fullscreen_lock=True.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import Quiz

def migrate():
    db = SessionLocal()
    try:
        # Find all exams with fullscreen_lock=False
        exams_to_fix = db.query(Quiz).filter(
            Quiz.is_exam == True,
            Quiz.fullscreen_lock == False
        ).all()
        
        count = len(exams_to_fix)
        if count == 0:
            print("No exams need fixing - all exams already have fullscreen_lock=True")
            return
        
        print(f"Found {count} exams with fullscreen_lock=False, fixing...")
        for quiz in exams_to_fix:
            quiz.fullscreen_lock = True
            print(f"  - Quiz {quiz.id}: '{quiz.title}' -> fullscreen_lock=True")
        
        db.commit()
        print(f"Successfully updated {count} exams")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()

# migrate_db.py
from app import create_app
from app.extensions import db
import sys

def migrate_database():
    """Add missing columns to quiz and question tables (PostgreSQL Compatible)"""
    app = create_app()
    
    with app.app_context():
        print(f"\n{'='*50}")
        print("DATABASE MIGRATION (PostgreSQL)")
        print(f"{'='*50}")

        try:
            # Use SQLAlchemy engine to connect
            with db.engine.connect() as connection:
                # We use a transaction so changes are atomic
                trans = connection.begin()
                
                # --- HELPER FUNCTION FOR POSTGRES ---
                def get_columns(table_name):
                    # Queries PostgreSQL information_schema instead of PRAGMA
                    query = "SELECT column_name FROM information_schema.columns WHERE table_name = :table"
                    result = connection.execute(db.text(query), {"table": table_name})
                    return [row[0] for row in result.fetchall()]

                # ========== UPDATE QUIZ TABLE ==========
                print("📊 Checking 'quiz' table...")
                columns = get_columns('quiz')
                
                if 'overall_timer' not in columns:
                    connection.execute(db.text('ALTER TABLE quiz ADD COLUMN overall_timer INTEGER'))
                    print("  ✅ Added overall_timer")
                else:
                    print("  - overall_timer exists")
                
                if 'show_leaderboard_global' not in columns:
                    connection.execute(db.text('ALTER TABLE quiz ADD COLUMN show_leaderboard_global BOOLEAN DEFAULT TRUE'))
                    print("  ✅ Added show_leaderboard_global")
                else:
                    print("  - show_leaderboard_global exists")

                # ========== UPDATE QUESTION TABLE ==========
                print("\n📊 Checking 'question' table...")
                columns = get_columns('question')
                
                # Column definitions (Name, Type, Default Value)
                # Note: String defaults must use single quotes inside the SQL string
                new_columns = [
                    ('question_text_plain', 'TEXT', None),
                    ('question_type', 'VARCHAR(50)', "'multiple-choice'"), # Note the single quotes for string literal
                    ('options', 'TEXT', None),
                    ('correct_answers', 'TEXT', None),
                    ('points', 'FLOAT', '1.0'),
                    ('show_leaderboard', 'BOOLEAN', 'TRUE'),
                    ('question_image', 'TEXT', None),
                    ('time_limit', 'INTEGER', '0')
                ]
                
                for col_name, col_type, default_val in new_columns:
                    if col_name not in columns:
                        # Construct query with/without default
                        if default_val:
                            query = f'ALTER TABLE question ADD COLUMN {col_name} {col_type} DEFAULT {default_val}'
                        else:
                            query = f'ALTER TABLE question ADD COLUMN {col_name} {col_type}'
                        
                        connection.execute(db.text(query))
                        print(f"  ✅ Added {col_name}")
                    else:
                        print(f"  - {col_name} exists")

                trans.commit()
                print(f"\n{'='*50}")
                print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
                print("   Please restart your Flask application.")
                print(f"{'='*50}")

        except Exception as e:
            print(f"\n❌ MIGRATION FAILED: {e}")
            # Ensure we don't leave the DB in a bad state if possible
            try:
                trans.rollback()
            except:
                pass

if __name__ == '__main__':
    migrate_database()
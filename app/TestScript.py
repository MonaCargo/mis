from sqlalchemy import text
from datetime import datetime, timezone

from app.db.session import session
from app.db.models.importOperation.oc_report import OcReport

# Check your database timezone
result = session.execute(text("SHOW TIMEZONE")).scalar()
print(f"Database Timezone: {result}")

# Check what func.now() actually generates
result = session.execute(text("SELECT NOW(), CURRENT_TIMESTAMP")).fetchone()
print(f"Database NOW(): {result[0]}")
print(f"Database CURRENT_TIMESTAMP: {result[1]}")

# Check actual UTC time
print(f"Python UTC now: {datetime.now(timezone.utc)}")

# Create a test record
test_report = OcReport(awb_no="DEBUG_TEST")
session.add(test_report)
session.commit()
session.refresh(test_report)

print(f"Saved created_at: {test_report.created_at}")
print(f"Difference from UTC: {datetime.now(timezone.utc).replace(tzinfo=None) - test_report.created_at}")
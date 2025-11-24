# app/services/igp_generator.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime


class IGPNumberGenerator:
    @staticmethod
    async def generate_bulk_igp_numbers(db: AsyncSession, count: int, date: datetime = None) -> list:
        """Generate multiple sequential IGP numbers efficiently"""
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime("%d%m%Y")  # DDMMYYYY
        
        # Get the last IGP number for today
        query = text("""
            SELECT igp_no 
            FROM oc_merge_gatepass 
            WHERE igp_no LIKE :pattern 
            ORDER BY id DESC 
            LIMIT 1
        """)
        
        pattern = f"OC{date_str}%"
        result = await db.execute(query, {"pattern": pattern})
        last_igp = result.scalar()
        
        if last_igp:
            serial_str = last_igp[10:]  # Get last 4 digits
            try:
                start_serial = int(serial_str) + 1
            except ValueError:
                start_serial = 1
        else:
            start_serial = 1
        
        # Generate sequential numbers
        igp_numbers = []
        for i in range(count):
            serial = start_serial + i
            serial_str = f"{serial:04d}"
            igp_number = f"OC{date_str}{serial_str}"
            igp_numbers.append(igp_number)
        
        # logger.info(f"Generated {count} IGP numbers from {igp_numbers[0]} to {igp_numbers[-1]}")
        return igp_numbers





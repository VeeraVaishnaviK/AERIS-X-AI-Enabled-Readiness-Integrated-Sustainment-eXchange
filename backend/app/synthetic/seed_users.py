import asyncio
from sqlalchemy import select
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal

DEMO_USERS = [
    {
        "username": "admin",
        "email": "admin@aeris-x.af.mil",
        "full_name": "Air Marshal V. Rao (Chief Architect)",
        "role": UserRole.ADMIN.value,
        "is_superuser": True,
    },
    {
        "username": "commander",
        "email": "commander@aeris-x.af.mil",
        "full_name": "Wing Commander Rajesh Sharma (Fleet Commander)",
        "role": UserRole.COMMANDER.value,
        "is_superuser": False,
    },
    {
        "username": "engineer",
        "email": "engineer@aeris-x.af.mil",
        "full_name": "Sqdn Ldr Vikram Sen (Senior Maintenance Engineer)",
        "role": UserRole.MAINTENANCE_ENGINEER.value,
        "is_superuser": False,
    },
    {
        "username": "logistics",
        "email": "logistics@aeris-x.af.mil",
        "full_name": "Flt Lt Ananya Iyer (Logistics & Supply Officer)",
        "role": UserRole.LOGISTICS_OFFICER.value,
        "is_superuser": False,
    },
    {
        "username": "technician",
        "email": "technician@aeris-x.af.mil",
        "full_name": "JWO K. Nair (Lead Avionics & Propulsion Specialist)",
        "role": UserRole.TECHNICIAN.value,
        "is_superuser": False,
    },
    {
        "username": "auditor",
        "email": "auditor@aeris-x.af.mil",
        "full_name": "Inspector P. Deshmukh (Defence Quality Assurance)",
        "role": UserRole.AUDITOR.value,
        "is_superuser": False,
    },
]

DEMO_PASSWORD = "AerisX@2026!"


async def seed_users() -> None:
    """Seed demo accounts for each of the 6 roles."""
    async with AsyncSessionLocal() as session:
        hashed = get_password_hash(DEMO_PASSWORD)
        for udata in DEMO_USERS:
            res = await session.execute(select(User).where(User.username == udata["username"]))
            existing = res.scalar_one_or_none()
            if not existing:
                user = User(
                    username=udata["username"],
                    email=udata["email"],
                    full_name=udata["full_name"],
                    hashed_password=hashed,
                    role=udata["role"],
                    is_active=True,
                    is_superuser=udata["is_superuser"],
                )
                session.add(user)
        await session.commit()
        print("Demo users successfully seeded for all 6 roles.")


if __name__ == "__main__":
    asyncio.run(seed_users())

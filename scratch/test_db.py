import asyncio
from backend.storage.db import get_db
from backend.native.service import NativeAttributionService

async def main():
    try:
        svc = NativeAttributionService()
        meeting_id = "fee6e2fc-24bf-4307-a22b-2e171b399a42"
        participants = [{"external_id": "Charin Patel", "display_name": "Charin Patel"}]
        print("Calling sync_participants...")
        res = await svc.sync_participants(meeting_id, participants)
        print("Result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

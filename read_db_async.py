import asyncio
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.speakers import SpeakersRepository

async def run():
    meetings_repo = MeetingsRepository()
    segments_repo = SegmentsRepository()
    speakers_repo = SpeakersRepository()

    meetings = await meetings_repo.list_all()
    if not meetings:
        print("No meetings found")
        return
    
    m = meetings[0]
    print(f"Latest Meeting: {m['id']} - {m['title']}")
    
    segments = await segments_repo.get_by_meeting(m['id'])
    print(f"Total Segments: {len(segments)}")
    for s in segments[:10]:
        print(f"  Segment: {s['start_time']:.1f} - {s['end_time']:.1f} [Speaker: {s['speaker']}, Display: {s.get('display_name')}] => {s['text']}")
        
    speakers = await speakers_repo.get_by_meeting(m['id'])
    print(f"Speakers in DB: {speakers}")

if __name__ == "__main__":
    asyncio.run(run())

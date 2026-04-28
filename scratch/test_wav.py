import struct
from pathlib import Path

def test_wav_header_finalization():
    test_file = Path("test_audio.wav")
    sample_rate = 16000
    
    # 1. Create a dummy WAV with initial header
    with open(test_file, 'wb') as fd:
        fd.write(b'RIFF')
        fd.write(struct.pack('<I', 0)) # Placeholder
        fd.write(b'WAVE')
        fd.write(b'fmt ')
        fd.write(struct.pack('<I', 16))
        fd.write(struct.pack('<H', 1))
        fd.write(struct.pack('<H', 1))
        fd.write(struct.pack('<I', sample_rate))
        fd.write(struct.pack('<I', sample_rate * 2))
        fd.write(struct.pack('<H', 2))
        fd.write(struct.pack('<H', 16))
        fd.write(b'data')
        fd.write(struct.pack('<I', 0)) # Placeholder
        
        # Write some dummy data (1 second of silence)
        fd.write(b'\x00' * (sample_rate * 2))
    
    print(f"Created file with size: {test_file.stat().st_size}")
    
    # 2. Finalize header
    file_size = test_file.stat().st_size
    data_size = file_size - 44
    riff_size = file_size - 8
    
    with open(test_file, 'r+b') as f:
        f.seek(4)
        f.write(struct.pack('<I', riff_size))
        f.seek(40)
        f.write(struct.pack('<I', data_size))
    
    print("Finalized header.")
    
    # 3. Verify with wave module
    import wave
    with wave.open(str(test_file), 'rb') as wf:
        print(f"Wave params: {wf.getparams()}")
        assert wf.getnframes() == sample_rate
        assert wf.getframerate() == sample_rate
        assert wf.getnchannels() == 1
    
    print("Verification successful!")
    test_file.unlink()

if __name__ == "__main__":
    test_wav_header_finalization()

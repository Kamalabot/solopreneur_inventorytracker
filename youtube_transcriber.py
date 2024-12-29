import yt_dlp
import os
import openai
import whisper
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import logging

class YouTubeTranscriber:
    def __init__(self, output_dir='transcriptions', use_openai=True, api_key=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_openai = use_openai
        
        # Setup logging
        logging.basicConfig(level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Initialize OpenAI if using API
        if use_openai:
            try:
                self.api_key = api_key or os.getenv('OPENAI_API_KEY')
                if not self.api_key:
                    raise ValueError("OpenAI API key not found. Please provide an API key or set OPENAI_API_KEY environment variable.")
                openai.api_key = self.api_key
            except Exception as e:
                self.logger.error(f"Error initializing OpenAI: {str(e)}")
                self.use_openai = False
                self.logger.info("Falling back to local Whisper model")
        
        # Initialize local Whisper model if not using OpenAI
        if not self.use_openai:
            try:
                self.logger.info("Loading local Whisper model...")
                self.model = whisper.load_model("base")
                self.logger.info("Local Whisper model loaded successfully")
            except Exception as e:
                self.logger.error(f"Error loading local Whisper model: {str(e)}")
                raise

    def format_timestamp(self, seconds):
        """Convert seconds to HH:MM:SS format"""
        return str(timedelta(seconds=int(seconds)))

    def download_audio(self, url):
        """Download audio from YouTube video"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': temp_file.name,
                    'quiet': True
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    self.logger.info("Downloading audio...")
                    info = ydl.extract_info(url, download=True)
                    return temp_file.name, info.get('title', 'Unknown Title'), info.get('duration', 0)
        except Exception as e:
            self.logger.error(f"Error downloading audio: {str(e)}")
            raise

    def transcribe_openai(self, audio_file):
        """Transcribe audio using OpenAI's Whisper API"""
        try:
            self.logger.info("Transcribing with OpenAI API...")
            with open(audio_file, 'rb') as f:
                response = openai.Audio.transcribe(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"]
                )
            return response
        except Exception as e:
            self.logger.error(f"Error transcribing with OpenAI: {str(e)}")
            raise

    def transcribe_local(self, audio_file):
        """Transcribe audio using local Whisper model"""
        try:
            self.logger.info("Transcribing with local Whisper model...")
            result = self.model.transcribe(
                audio_file,
                word_timestamps=True,
                verbose=True
            )
            return result
        except Exception as e:
            self.logger.error(f"Error transcribing with local Whisper: {str(e)}")
            raise

    def save_transcription(self, transcription, video_title, duration):
        """Save transcription to files with timestamps"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_title = "".join(x for x in video_title if x.isalnum() or x in (' ', '-', '_'))
            base_path = self.output_dir / f"{safe_title}_{timestamp}"

            # Save JSON with full transcription data
            json_path = base_path.with_suffix('.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(transcription, f, ensure_ascii=False, indent=2)

            # Save timestamped transcription
            text_path = base_path.with_suffix('.txt')
            srt_path = base_path.with_suffix('.srt')

            with open(text_path, 'w', encoding='utf-8') as txt_file, \
                 open(srt_path, 'w', encoding='utf-8') as srt_file:
                
                if self.use_openai:
                    # Process OpenAI response
                    segments = transcription.get('segments', [])
                    for i, segment in enumerate(segments, 1):
                        start_time = self.format_timestamp(segment['start'])
                        end_time = self.format_timestamp(segment['end'])
                        text = segment['text'].strip()

                        # Write to text file with timestamps
                        txt_file.write(f"[{start_time} --> {end_time}] {text}\n")

                        # Write to SRT file
                        srt_file.write(f"{i}\n")
                        srt_file.write(f"{start_time},000 --> {end_time},000\n")
                        srt_file.write(f"{text}\n\n")
                else:
                    # Process local Whisper response
                    segments = transcription.get('segments', [])
                    for i, segment in enumerate(segments, 1):
                        start_time = self.format_timestamp(segment['start'])
                        end_time = self.format_timestamp(segment['end'])
                        text = segment['text'].strip()

                        # Write to text file with timestamps
                        txt_file.write(f"[{start_time} --> {end_time}] {text}\n")

                        # Write to SRT file
                        srt_file.write(f"{i}\n")
                        srt_file.write(f"{start_time},000 --> {end_time},000\n")
                        srt_file.write(f"{text}\n\n")

            return {
                'json_path': str(json_path),
                'text_path': str(text_path),
                'srt_path': str(srt_path)
            }
        except Exception as e:
            self.logger.error(f"Error saving transcription: {str(e)}")
            raise

    def transcribe_video(self, url):
        """Main method to transcribe a YouTube video"""
        try:
            # Download audio
            audio_file, video_title, duration = self.download_audio(url)
            self.logger.info(f"Audio downloaded: {video_title}")

            try:
                # Transcribe audio
                if self.use_openai:
                    transcription = self.transcribe_openai(audio_file)
                else:
                    transcription = self.transcribe_local(audio_file)

                # Save transcription
                paths = self.save_transcription(transcription, video_title, duration)
                self.logger.info(f"Transcription saved: {paths['text_path']}")

                return {
                    'title': video_title,
                    'duration': duration,
                    'paths': paths,
                    'transcription': transcription
                }

            finally:
                # Clean up temporary audio file
                if os.path.exists(audio_file):
                    os.remove(audio_file)

        except Exception as e:
            self.logger.error(f"Error transcribing video: {str(e)}")
            raise

def main():
    # Get API key from environment or user input
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        api_key = input("Enter your OpenAI API key (press Enter to use local model): ").strip()
    
    use_openai = bool(api_key)
    
    try:
        transcriber = YouTubeTranscriber(use_openai=use_openai, api_key=api_key)
        
        while True:
            url = input("\nEnter YouTube URL (or 'quit' to exit): ")
            if url.lower() == 'quit':
                break
                
            print("\nProcessing video...")
            try:
                result = transcriber.transcribe_video(url)
                print(f"\nTranscription completed successfully!")
                print(f"Video: {result['title']}")
                print(f"Duration: {timedelta(seconds=int(result['duration']))}")
                print(f"Files saved:")
                print(f"- JSON: {result['paths']['json_path']}")
                print(f"- Text with timestamps: {result['paths']['text_path']}")
                print(f"- SRT subtitles: {result['paths']['srt_path']}")
            except Exception as e:
                print(f"Error processing video: {str(e)}")
                continue

    except Exception as e:
        print(f"Error initializing transcriber: {str(e)}")

if __name__ == "__main__":
    main() 
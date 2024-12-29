import torch
from TTS.api import TTS
import os
import logging
from pathlib import Path
from datetime import datetime
import json
import numpy as np
import soundfile as sf
import tempfile

class TextToSpeech:
    def __init__(self, model_name="tts_models/en/ljspeech/tacotron2-DDC", 
                 output_dir='tts_output'):
        """
        Initialize TTS with specified model.
        Available models can be listed using: TTS.list_models()
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        try:
            self.logger.info(f"Loading TTS model: {model_name}")
            self.tts = TTS(model_name)
            self.logger.info("TTS model loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading TTS model: {str(e)}")
            raise

    @staticmethod
    def list_available_models():
        """List all available TTS models"""
        return TTS.list_models()

    def process_text(self, text, output_path=None, speaker=None, language=None):
        """
        Convert text to speech and save to file.
        Returns path to the saved audio file.
        """
        try:
            # Create temporary file for processing
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                self.logger.info("Generating speech...")
                
                # Generate speech
                self.tts.tts_to_file(
                    text=text,
                    file_path=temp_file.name,
                    speaker=speaker,
                    language=language
                )
                
                # If no output path specified, create one
                if output_path is None:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    safe_text = "".join(x for x in text[:30] if x.isalnum() or x in (' ', '-', '_'))
                    output_path = self.output_dir / f"tts_{safe_text}_{timestamp}.wav"
                
                # Move from temp file to final location
                os.replace(temp_file.name, output_path)
                
                self.logger.info(f"Audio saved to: {output_path}")
                return str(output_path)

        except Exception as e:
            self.logger.error(f"Error generating speech: {str(e)}")
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            raise

    def process_file(self, input_file, output_dir=None, speaker=None, language=None):
        """
        Process a text file and convert to speech.
        Supports txt and json files.
        """
        try:
            input_path = Path(input_file)
            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_file}")

            # Determine output directory
            if output_dir is None:
                output_dir = self.output_dir / input_path.stem
            else:
                output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process based on file type
            if input_path.suffix.lower() == '.txt':
                return self._process_txt_file(input_path, output_dir, speaker, language)
            elif input_path.suffix.lower() == '.json':
                return self._process_json_file(input_path, output_dir, speaker, language)
            else:
                raise ValueError(f"Unsupported file type: {input_path.suffix}")

        except Exception as e:
            self.logger.error(f"Error processing file: {str(e)}")
            raise

    def _process_txt_file(self, input_path, output_dir, speaker=None, language=None):
        """Process a plain text file"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = output_dir / f"tts_{timestamp}.wav"
            
            return self.process_text(text, output_path, speaker, language)

        except Exception as e:
            self.logger.error(f"Error processing text file: {str(e)}")
            raise

    def _process_json_file(self, input_path, output_dir, speaker=None, language=None):
        """Process a JSON file with timestamps"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_paths = []

            # Handle different JSON formats
            if isinstance(data, dict) and 'segments' in data:
                # Process segments
                for i, segment in enumerate(data['segments']):
                    text = segment.get('text', '').strip()
                    if text:
                        output_path = output_dir / f"tts_segment_{i:04d}_{timestamp}.wav"
                        path = self.process_text(text, output_path, speaker, language)
                        output_paths.append({
                            'segment': i,
                            'text': text,
                            'audio_path': path,
                            'start': segment.get('start'),
                            'end': segment.get('end')
                        })
            else:
                # Process as single text
                text = str(data)
                output_path = output_dir / f"tts_{timestamp}.wav"
                path = self.process_text(text, output_path, speaker, language)
                output_paths.append({
                    'text': text,
                    'audio_path': path
                })

            # Save metadata
            metadata_path = output_dir / f"tts_metadata_{timestamp}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(output_paths, f, ensure_ascii=False, indent=2)

            return output_paths

        except Exception as e:
            self.logger.error(f"Error processing JSON file: {str(e)}")
            raise

def main():
    try:
        # Initialize TTS
        tts = TextToSpeech()
        
        while True:
            print("\nText-to-Speech Converter")
            print("1. Convert text input")
            print("2. Convert from file")
            print("3. List available models")
            print("4. Quit")
            
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                text = input("\nEnter the text to convert: ")
                try:
                    output_path = tts.process_text(text)
                    print(f"\nAudio saved to: {output_path}")
                except Exception as e:
                    print(f"Error: {str(e)}")
                    
            elif choice == '2':
                file_path = input("\nEnter the path to your text/json file: ")
                try:
                    output_paths = tts.process_file(file_path)
                    print("\nProcessing complete!")
                    print("Generated audio files:")
                    for item in output_paths:
                        print(f"- {item['audio_path']}")
                except Exception as e:
                    print(f"Error: {str(e)}")
                    
            elif choice == '3':
                models = tts.list_available_models()
                print("\nAvailable models:")
                for model in models:
                    print(f"- {model}")
                    
            elif choice == '4':
                break
                
            else:
                print("Invalid choice. Please try again.")

    except Exception as e:
        print(f"Error initializing TTS: {str(e)}")

if __name__ == "__main__":
    main() 
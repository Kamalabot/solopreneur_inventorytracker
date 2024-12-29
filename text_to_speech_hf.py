from transformers import SpeechT5Processor, SpeechT5ForTextToSpeech, SpeechT5HifiGan
import torch
import soundfile as sf
from datasets import load_dataset
import numpy as np
import os
import logging
from pathlib import Path
from datetime import datetime
import json
import tempfile
from typing import Optional, List, Dict, Union

class TextToSpeechHF:
    def __init__(
        self, 
        model_name: str = "microsoft/speecht5_tts",
        vocoder_name: str = "microsoft/speecht5_hifigan",
        output_dir: str = 'tts_output'
    ):
        """
        Initialize TTS with Hugging Face models.
        Args:
            model_name: Name of the TTS model from Hugging Face
            vocoder_name: Name of the vocoder model
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        try:
            # Load models and processor
            self.logger.info(f"Loading TTS model: {model_name}")
            self.processor = SpeechT5Processor.from_pretrained(model_name)
            self.model = SpeechT5ForTextToSpeech.from_pretrained(model_name)
            self.vocoder = SpeechT5HifiGan.from_pretrained(vocoder_name)
            
            # Load speaker embeddings
            self.logger.info("Loading speaker embeddings...")
            dataset = load_dataset("Matthijs/cmu-arctic-xvectors", split="validation")
            self.speaker_embeddings = torch.tensor(dataset[7306]["xvector"]).unsqueeze(0)
            
            # Set device
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(self.device)
            self.vocoder.to(self.device)
            
            self.logger.info(f"Models loaded successfully. Using device: {self.device}")
            
        except Exception as e:
            self.logger.error(f"Error initializing models: {str(e)}")
            raise

    def process_text(
        self, 
        text: str, 
        output_path: Optional[str] = None,
        speaker_embeddings: Optional[torch.Tensor] = None,
        sample_rate: int = 16000
    ) -> str:
        """
        Convert text to speech and save to file.
        Args:
            text: Input text to convert
            output_path: Optional path to save audio file
            speaker_embeddings: Optional custom speaker embeddings
            sample_rate: Audio sample rate
        Returns:
            Path to the saved audio file
        """
        try:
            # Create temporary file for processing
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                self.logger.info("Generating speech...")
                
                # Process text
                inputs = self.processor(text=text, return_tensors="pt").to(self.device)
                
                # Use provided or default speaker embeddings
                embeddings = (speaker_embeddings if speaker_embeddings is not None 
                            else self.speaker_embeddings.to(self.device))
                
                # Generate speech
                speech = self.model.generate_speech(
                    inputs["input_ids"],
                    embeddings,
                    vocoder=self.vocoder
                )
                
                # Convert to numpy and save
                speech = speech.cpu().numpy()
                
                # If no output path specified, create one
                if output_path is None:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    safe_text = "".join(x for x in text[:30] if x.isalnum() or x in (' ', '-', '_'))
                    output_path = self.output_dir / f"tts_{safe_text}_{timestamp}.wav"
                
                # Save audio file
                sf.write(str(output_path), speech, sample_rate)
                
                self.logger.info(f"Audio saved to: {output_path}")
                return str(output_path)

        except Exception as e:
            self.logger.error(f"Error generating speech: {str(e)}")
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            raise

    def process_file(
        self, 
        input_file: str, 
        output_dir: Optional[str] = None,
        sample_rate: int = 16000
    ) -> List[Dict[str, str]]:
        """
        Process a text file and convert to speech.
        Args:
            input_file: Path to input text or JSON file
            output_dir: Optional custom output directory
            sample_rate: Audio sample rate
        Returns:
            List of dictionaries containing file metadata
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
                return self._process_txt_file(input_path, output_dir, sample_rate)
            elif input_path.suffix.lower() == '.json':
                return self._process_json_file(input_path, output_dir, sample_rate)
            else:
                raise ValueError(f"Unsupported file type: {input_path.suffix}")

        except Exception as e:
            self.logger.error(f"Error processing file: {str(e)}")
            raise

    def _process_txt_file(
        self, 
        input_path: Path, 
        output_dir: Path,
        sample_rate: int = 16000
    ) -> List[Dict[str, str]]:
        """Process a plain text file"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()

            # Split text into manageable chunks (e.g., by sentences)
            chunks = self._split_text(text)
            output_paths = []

            for i, chunk in enumerate(chunks):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = output_dir / f"tts_chunk_{i:04d}_{timestamp}.wav"
                
                path = self.process_text(
                    chunk, 
                    str(output_path),
                    sample_rate=sample_rate
                )
                
                output_paths.append({
                    'chunk': i,
                    'text': chunk,
                    'audio_path': path
                })

            # Save metadata
            metadata_path = output_dir / f"tts_metadata_{timestamp}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(output_paths, f, ensure_ascii=False, indent=2)

            return output_paths

        except Exception as e:
            self.logger.error(f"Error processing text file: {str(e)}")
            raise

    def _process_json_file(
        self, 
        input_path: Path, 
        output_dir: Path,
        sample_rate: int = 16000
    ) -> List[Dict[str, str]]:
        """Process a JSON file with timestamps"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_paths = []

            if isinstance(data, dict) and 'segments' in data:
                # Process segments
                for i, segment in enumerate(data['segments']):
                    text = segment.get('text', '').strip()
                    if text:
                        output_path = output_dir / f"tts_segment_{i:04d}_{timestamp}.wav"
                        path = self.process_text(
                            text, 
                            str(output_path),
                            sample_rate=sample_rate
                        )
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
                path = self.process_text(
                    text, 
                    str(output_path),
                    sample_rate=sample_rate
                )
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

    @staticmethod
    def _split_text(text: str, max_length: int = 200) -> List[str]:
        """Split text into manageable chunks"""
        # Simple sentence splitting
        sentences = text.replace('\n', ' ').split('.')
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence = sentence.strip() + '.'
            sentence_length = len(sentence)
            
            if current_length + sentence_length > max_length and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
            
            current_chunk.append(sentence)
            current_length += sentence_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

def main():
    try:
        # Initialize TTS
        tts = TextToSpeechHF()
        
        while True:
            print("\nText-to-Speech Converter (Hugging Face)")
            print("1. Convert text input")
            print("2. Convert from file")
            print("3. Quit")
            
            choice = input("\nEnter your choice (1-3): ").strip()
            
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
                break
                
            else:
                print("Invalid choice. Please try again.")

    except Exception as e:
        print(f"Error initializing TTS: {str(e)}")

if __name__ == "__main__":
    main() 
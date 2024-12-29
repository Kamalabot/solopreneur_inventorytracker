from yt_dlp import YoutubeDL
import json
from datetime import datetime
import os

class YouTubeExtractor:
    def __init__(self, output_dir='youtube_data'):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def extract_channel_data(self, url):
        try:
            # First get the channel URL
            with YoutubeDL({
                'quiet': True,
                'extract_flat': True
            }) as ydl:
                info = ydl.extract_info(url, download=False)
                channel_url = info.get('channel_url') or info.get('uploader_url')
                channel_name = info.get('uploader') or info.get('channel')
                
                if not channel_url:
                    print("Could not find channel URL")
                    return None

            # Configure YoutubeDL for channel extraction
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'force_generic_extractor': False,
                'ignoreerrors': True,
                'extract_flat_playlist': True,
                'playlist_items': '1-1000',  # Try to get up to 1000 videos
                'max_downloads': 1000,
                'break_on_reject': False,
                'no_warnings': True
            }
            
            print(f"Fetching all videos from channel: {channel_url}")
            with YoutubeDL(ydl_opts) as ydl:
                channel_info = ydl.extract_info(channel_url, download=False)
                
                if not channel_info:
                    print("No channel information found")
                    return None

                videos = []
                if 'entries' in channel_info:
                    # Process all videos in the channel
                    for entry in channel_info['entries']:
                        if entry and entry.get('title') and entry.get('id'):
                            video = {
                                'video_id': entry.get('id'),
                                'title': entry.get('title'),
                                'url': f'https://youtube.com/watch?v={entry.get("id")}',
                                'channel_name': channel_name,
                                'upload_date': entry.get('upload_date', ''),
                                'duration': entry.get('duration', 0),
                                'view_count': entry.get('view_count', 0)
                            }
                            videos.append(video)
                            print(f"Found video: {video['title']}")

                    if videos:
                        # Save the data
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        safe_channel_name = "".join(x for x in channel_name if x.isalnum() or x in (' ', '-', '_'))
                        
                        # Save JSON with all video data
                        json_file = os.path.join(self.output_dir, f"{safe_channel_name}_{timestamp}.json")
                        with open(json_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                'channel_name': channel_name,
                                'video_count': len(videos),
                                'extraction_date': datetime.now().isoformat(),
                                'videos': videos
                            }, f, ensure_ascii=False, indent=2)

                        # Save titles to text file
                        txt_file = os.path.join(self.output_dir, f"{safe_channel_name}_{timestamp}_titles.txt")
                        with open(txt_file, 'w', encoding='utf-8') as f:
                            for video in videos:
                                f.write(f"{video['title']}\n")

                        print(f"\nExtracted {len(videos)} videos from {channel_name}")
                        print(f"JSON saved to: {json_file}")
                        print(f"Titles saved to: {txt_file}")

                        return {
                            'channel_name': channel_name,
                            'video_count': len(videos),
                            'videos': videos,
                            'json_file': json_file,
                            'txt_file': txt_file
                        }
                
                print("No videos found in channel")
                return None

        except Exception as e:
            print(f"Error extracting channel data: {str(e)}")
            return None

def main():
    extractor = YouTubeExtractor()
    
    while True:
        url = input("\nEnter YouTube channel or video URL (or 'quit' to exit): ")
        if url.lower() == 'quit':
            break
            
        print("\nExtracting channel data...")
        result = extractor.extract_channel_data(url)
        
        if result:
            print(f"\nSuccessfully extracted {result['video_count']} videos from {result['channel_name']}")
            print(f"Files saved in the youtube_data directory")
        else:
            print("Failed to extract channel data")

if __name__ == "__main__":
    main() 
# ==========================================
# 📦 DEPENDÊNCIAS
# ==========================================
import os, shutil, glob, requests
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from rapidfuzz import fuzz
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 🎵 SPOTIFY API SETUP
# ==========================================
SPOTIFY_CLIENT_ID = 'a329b4abe42c46c8928c082816bc8d36'
SPOTIFY_CLIENT_SECRET = '2d23bae3182b44f38662abf837a26fe7'

auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID,
                                        client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(auth_manager=auth_manager)

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================
def is_match(spotify_track, yt_info, threshold=70):
    title_spotify = spotify_track['name'].lower()
    title_yt = yt_info.get('title', '').lower()
    title_ratio = fuzz.token_set_ratio(title_spotify, title_yt)

    artists_spotify = [a['name'].lower() for a in spotify_track['artists']]
    artist_ratio = max(fuzz.token_set_ratio(artist, title_yt) for artist in artists_spotify)

    duration_spotify = spotify_track['duration_ms'] / 1000
    duration_yt = yt_info.get('duration', 0)
    duration_diff = abs(duration_spotify - duration_yt)

    return title_ratio >= threshold and artist_ratio >= threshold and duration_diff <= 10


def tag_mp3(file_path, title, artist, album, album_art_url):
    try:
        audio = MP3(file_path, ID3=ID3)
        audio.add_tags()
    except:
        pass  # já tem tags

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))

    try:
        if album_art_url:
            img_data = requests.get(album_art_url).content
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
    except Exception as e:
        print(f"⚠️ Erro ao buscar capa: {e}")

    audio.save()


# ==========================================
# ⚡ DOWNLOAD DE UMA MÚSICA
# ==========================================
MAX_CONCURRENT = 3

def download_single_track(track, folder):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{folder}/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    query = f"{track['name']} {track['artists'][0]['name']}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = results.get('entries', [])
            match = None
            best_diff = None

            for entry in entries:
                if is_match(track, entry):
                    match = entry
                    break
                else:
                    title_ratio = fuzz.token_set_ratio(track['name'].lower(), entry['title'].lower())
                    artist_ratio = max(fuzz.token_set_ratio(a['name'].lower(), entry['title'].lower()) for a in track['artists'])
                    duration_diff = abs(track['duration_ms'] / 1000 - entry.get('duration', 0))
                    if best_diff is None or title_ratio + artist_ratio > best_diff["score_sum"]:
                        best_diff = {
                            "spotify": f"{track['name']} - {track['artists'][0]['name']}",
                            "yt_title": entry['title'],
                            "title_ratio": title_ratio,
                            "artist_ratio": artist_ratio,
                            "duration_diff": duration_diff,
                            "webpage_url": entry['webpage_url'],
                            "track": track,
                            "score_sum": title_ratio + artist_ratio
                        }

            if match:
                ydl.download([match['webpage_url']])
                mp3_files = glob.glob(f"{folder}/*.mp3")
                if mp3_files:
                    latest = max(mp3_files, key=os.path.getmtime)
                    tag_mp3(latest, track['name'], track['artists'][0]['name'], track['album']['name'], track['album']['images'][0]['url'])
                return f"✅ {track['name']} - {track['artists'][0]['name']}"
            else:
                return best_diff

    except Exception as e:
        return f"❌ Erro: {track['name']} — {e}"


# ==========================================
# 🚀 FUNÇÃO PRINCIPAL
# ==========================================
def download_spotify_content(url):
    if not url.startswith("https://open.spotify.com/"):
        print("❌ URL inválida.")
        return

    # Identifica tipo de link
    if "playlist" in url:
        info = sp.playlist(url)
        title = info['name']
        tracks = [item['track'] for item in info['tracks']['items']]
    elif "album" in url:
        info = sp.album(url)
        title = info['name']
        tracks = info['tracks']['items']
        for t in tracks: t['album'] = info
    elif "track" in url:
        info = sp.track(url)
        title = info['name']
        tracks = [info]
    else:
        print("❌ Tipo de URL não suportado.")
        return

    folder = f"./{title.replace('/', '_')}"
    os.makedirs(folder, exist_ok=True)

    print(f"🎧 Iniciando '{title}' — {len(tracks)} músicas.\n")

    failed_matches = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = [executor.submit(download_single_track, t, folder) for t in tracks]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            print(f"🎵 Progresso: {completed}/{len(tracks)}")
            if isinstance(result, dict):
                failed_matches.append(result)
                print(f"⚠️ Pendentes: {result['spotify']}")
            else:
                print(result)

    # Criar arquivo ZIP
    zip_path = f"{title.replace('/', '_')}.zip"
    shutil.make_archive(zip_path.replace('.zip', ''), 'zip', folder)
    print(f"\n✅ Concluído! Arquivos ZIP: {zip_path}")


# ==========================================
# 🔹 EXECUTAR SCRIPT
# ==========================================
if __name__ == "__main__":
    spotify_url = input("🎵 Insere o link do Spotify (track/album/playlist): ").strip()
    download_spotify_content(spotify_url)

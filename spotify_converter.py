# spotify_converter_app.py

import os
import shutil
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
from rapidfuzz import fuzz
import streamlit as st

# ==========================================
# SPOTIFY API
# ==========================================
SPOTIFY_CLIENT_ID = 'a329b4abe42c46c8928c082816bc8d36'
SPOTIFY_CLIENT_SECRET = '2d23bae3182b44f38662abf837a26fe7'

auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(auth_manager=auth_manager)

# ==========================================
# Funções auxiliares
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
        pass
    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    try:
        if album_art_url:
            img_data = requests.get(album_art_url).content
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
    except Exception as e:
        st.warning(f"Erro no cover: {e}")
    audio.save()

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
            for entry in entries:
                if is_match(track, entry):
                    match = entry
                    break
            if match:
                ydl.download([match['webpage_url']])
                mp3_files = glob.glob(f"{folder}/*.mp3")
                if mp3_files:
                    latest = max(mp3_files, key=os.path.getmtime)
                    tag_mp3(latest, track['name'], track['artists'][0]['name'], track['album']['name'], track['album']['images'][0]['url'])
                return f"✅ {track['name']} - {track['artists'][0]['name']}"
            else:
                return f"⚠️ Sem match para {track['name']}"
    except Exception as e:
        return f"❌ Erro: {track['name']} — {e}"

def download_spotify_content(url):
    status_messages = []
    if not url.startswith("https://open.spotify.com/"):
        status_messages.append("❌ URL inválida!")
        return status_messages

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
        status_messages.append("❌ Tipo de URL não suportado")
        return status_messages

    folder = f"downloads/{title.replace('/', '_')}"
    os.makedirs(folder, exist_ok=True)

    status_messages.append(f"🎧 Iniciando '{title}' — {len(tracks)} tracks.\n")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = [executor.submit(download_single_track, t, folder) for t in tracks]
        for future in futures:
            result = future.result()
            status_messages.append(result)

    zip_path = shutil.make_archive(folder, 'zip', folder)
    status_messages.append(f"\n✅ Todos os arquivos estão em {zip_path}")
    return status_messages

# ==========================================
# STREAMLIT FRONTEND
# ==========================================
st.title("Spotify to MP3 Converter")

spotify_url = st.text_input("Cole a URL do Spotify (track/album/playlist):")

if st.button("Converter"):
    if spotify_url:
        messages = download_spotify_content(spotify_url)
        for msg in messages:
            st.write(msg)


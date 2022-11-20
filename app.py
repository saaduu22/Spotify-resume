import ast
import random
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from flask import Flask, url_for, session, request, redirect, render_template
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)

app.secret_key = 'SOMETHING-RANDOM'
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

# initialize sqllite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)

# create user object to store data in
# store data so that we can limit number of API calls
class User(db.Model):
    id = db.Column(db.String, primary_key=True)
    top_tracks = db.Column(db.String)
    top_artists = db.Column(db.String)
    top_genres = db.Column(db.String)

    def __repr__(self):
        return f'user({self.id}, {self.top_tracks}, {self.top_artists}, {self.top_genres})'

app.app_context().push()


# homepage FE only
@app.route('/')
def home_page():
    return render_template('home.html')

# resume page, FE only
@app.route('/resume')
def resume_detail():
    return render_template('resume.html')

# Login page, this doesn't ever get viewed by the user, but the session attribute is used to know if the user wants to contribute to the playlist
@app.route('/login')
def login():
    session['attribute'] = request.args.get('attribute')
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

# spotiy Oauth page, generate spotiy token and then redirect to playlist page
@app.route('/authorize')
def authorize():
    sp_oauth = create_spotify_oauth()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session["token_info"] = token_info
    return redirect("/playlist")


# playlist page
@app.route('/playlist', methods=['GET', 'POST'])
def playlist():
    # use try and except because users will be redirected to the same page with different data depending on query strings
    try:
        # See if user has chosen to contribute to playlsit, if so, add their preferences to the playlist
        if session['attribute'] == 'contribute':
            add_playlist()
        else:
        # just make user follow playlsit
            follow_play()
        return render_template('/playlist.html')
    # Render FE just as is without
    except KeyError:
        return render_template('/playlist.html')

# WIP ignore for now
'''
@app.route('/about')
def about():
    return render_template('/about.html')
'''

# add the users preferences to the playlist
def add_playlist():
    # get token info from OAuth
    session['token_info'], authorized = get_token()
    session.modified = False
    # make sure user is authorized, if not, redirect to homepage
    if not authorized:
        return redirect('/')
    # authenticate user and create object
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    # save artsist, genre, and track data into database
    top_data = save_tracks_artists(sp)
    list_tracks = top_data[0]
    list_artists = top_data[1]
    list_genres = top_data[2]
    # save user data in database
    data_user = sp.current_user()
    # get user ID to add to user object
    user_id = data_user['id']
    # Check if user doesn't exist in db, create new one
    # if user already exists, don't double count in calculations
    if not User.query.filter_by(id=user_id).all():
        user_data = User(id=user_id, top_tracks=str(list_tracks), top_artists=str(list_artists), top_genres=str(list_genres))
        db.session.add(user_data)
        db.session.commit()
    return

# if user saves playlist, make them follow it on their spotify
def follow_play():
    # authenticate user
    session['token_info'], authorized = get_token()
    session.modified = False
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    # add playlist to followed for the users account
    sp.current_user_follow_playlist(playlist_id='7JKLTBeVXssnuU8ECIBzAD')

# create lists of users top artists, genres and tracks
def save_tracks_artists(sp):
    top_tracks_list = []
    top_artists_list = []
    count = 0
    # get maximum number of artists/tracks without breaking API limits and save them to list
    while count < 5:
        offset_track = sp.current_user_top_tracks(limit=20, offset=count)
        top_artists = sp.current_user_top_artists(limit=10, offset=count)
        count += 1
        top_tracks_list.append(offset_track)
        top_artists_list.append(top_artists)
    # from artists, get their associated genres and the artists ID as well
    artist_genre = get_artistsGenre(top_artists_list)
    # list of artist IDs
    top_artists = artist_genre[0]
    # list of artist genres
    top_genres = artist_genre[1]
    # get track URIs to be used later
    top_tracks = []
    for batch_tracks in top_tracks_list:
        for ind_tracks in batch_tracks['items']:
            top_tracks.append(ind_tracks['uri'])
    # create dictionary of top track URIs
    top_tracks = list(dict.fromkeys(top_tracks))
    return top_tracks, top_artists, top_genres

# get genres assocated with artists and the artists ID
def get_artistsGenre(top_artists):
    artist_list = []
    genres = []
    for x in top_artists:
        for a in x['items']:
            artist_list.append(a['id'])
            genres.append(a['genres'])
    return artist_list, genres

# check to see if token is valid and if not (Expired) then regenerate token
def get_token():
    token_valid = False
    token_info = session.get("token_info", {})

    # Checking if the session already has a token stored
    if not (session.get('token_info', False)):
        token_valid = False
        return token_info, token_valid

    # Checking if token has expired
    now = int(time.time())
    is_token_expired = session.get('token_info').get('expires_at') - now < 60

    # Refreshing token if it has expired
    if (is_token_expired):
        sp_oauth = create_spotify_oauth()
        token_info = sp_oauth.refresh_access_token(session.get('token_info').get('refresh_token'))

    token_valid = True
    return token_info, token_valid


# Spotify Application information
def create_spotify_oauth():
    return SpotifyOAuth(
            client_id="client id from spotify dev app",
            client_secret="client secret from spotify dev app",
            redirect_uri=url_for('authorize', _external=True),
            scope="user-top-read user-library-read playlist-modify-public playlist-modify-private")

# from all of the tracks saved, get a list of 20 to be added to playlist and randomize them and ensure same number of songs per users are shown
def get_sample(total_users, all_list):
    total_number = 20
    ind_number = total_number / total_users
    final_list = []
    # Iterate through all tracks in database and create a list for each user then create a list of final tracks from all users
    for y in all_list:
        list_of = ast.literal_eval(y[0])
        list_sample = random.sample(list_of, int(ind_number))
        final_list.extend(list_sample)
    return final_list


if __name__ == '__main__':
    app.run(debug=True)

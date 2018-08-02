import sys
import json
import os

from urllib.request import urlretrieve
from pprint import pprint
from pathlib import Path

#for rss parsing
from xml.dom import minidom

import traceback
import time
import datetime


import httplib2
import re

from apiclient.discovery import build_from_document
from apiclient.errors import HttpError
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow


import xml.etree.cElementTree as ET


# Imports the Google Cloud client library (use beta for the advanced model for speech recognition)
import google.cloud.speech_v1p1beta1 as speech
from google.cloud import storage

import subprocess
from subprocess import Popen, PIPE
import shlex

# Instantiates a client
storage_client = storage.Client()

# constants
bucket_name = 'natranscript'
rssfeeduri = "http://feed.nashownotes.com/rss.xml"

commonNoAgendaPhrases = ['No Agenda', 'crackpot','buzzkill','drone star state','nbc','msnbc','media assasination','CIA','dvorak','curry',
						 'knighting','ITM','NJNK', 'LGY', 'karma' , 'F. cancer','Sir.' , 'Donate', 'Dvorak.org/NA', 'call me a cab',
						 'value for value','commonlaw', 'cludio','Zephyr', "John C. Dvorak"]

videoid=""

CLIENT_SECRETS_FILE = "client_secrets.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
YOUTUBE_READ_WRITE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:
   %s
with information from the APIs Console
https://console.developers.google.com

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),CLIENT_SECRETS_FILE))




# Authorize the request and store authorization credentials.
def get_authenticated_service(args):
  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_READ_WRITE_SSL_SCOPE,
    message=MISSING_CLIENT_SECRETS_MESSAGE)

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  # Trusted testers can download this discovery document from the developers page
  # and it should be in the same directory with the code.
  with open("youtube-v3-api-captions.json", "r") as f:
    doc = f.read()
    return build_from_document(doc, http=credentials.authorize(httplib2.Http()))


# Call the API's captions.list method to list the existing caption tracks.
def list_captions(youtube, video_id):
  results = youtube.captions().list(
    part="snippet",
    videoId=video_id
  ).execute()

  if( len(results["items"]) > 0):
	  item = results["items"][0]
	  return item["id"]
  else:
	  return ""
  #for item in results["items"]:
  #  id = item["id"]
  #  name = item["snippet"]["name"]
  #  language = item["snippet"]["language"]
  #  print ("Caption track '%s(%s)' in '%s' language." % (name, id, language))
  #return results["items"]


# Call the API's captions.download method to download an existing caption track.
def download_caption(youtube, caption_id, tfmt, hfile):
	subtitle = youtube.captions().download(id=caption_id,tfmt=tfmt).execute()

	hfile.write("<div id=\"player\" name=\"" + videoid + "\"></div>")
	# hfile.write("https://youtu.be/" + videoid)
	hfile.write("\n\n")

	#print ("First line of caption track: %s" % (subtitle) )
	strresult = subtitle.decode('utf-8')
	#print ("--: %s" % (strresult) )
	sections=re.split("\n\n", strresult)
	lastTime=0
	for line in sections:
		#print ( "* %s" % line)
		three = line.splitlines()
		if( len(three) >= 3):
			timearr = re.split( " --> ", three[1])
			slowtime = timearr[0].split(',')[0]
			slowtime = slowtime[1:]

			x = time.strptime(slowtime, '%H:%M:%S')
			currentSeconds = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds()
			print ( ("%s : %s") % (slowtime, currentSeconds))

			paragraphoutline = three[2]
			htmlLine1 = paragraphoutline
			opmlLine = paragraphoutline
			if len(paragraphoutline.split()) > 1:
				(firstword, restword) = paragraphoutline.split(' ', 1)
				htmlLine1 = "<a title='click 2 play' href=\"javascript:jmpyt('" + videoid + "','" + slowtime + "');\"  target=\"yt\">" + firstword + "</a> " + restword
				paragraphoutline = "<a target='yt' title='click to play' href='https://youtu.be/" + videoid + "?t=" + slowtime + "'>" + firstword + "</a> " + restword
			else:
				htmlLine1 = "<a title='click 2 play' href=\"javascript:jmpyt('" + videoid + "','" + slowtime + "');\"  target=\"yt\">" + paragraphoutline + "</a> "
				paragraphoutline = "<a target='yt' title='click to play' href='https://youtu.be/" + videoid + "?t=" + slowtime + "'>" + paragraphoutline + "</a> " + restword

			print ( htmlLine1)
			hfile.write(htmlLine1)
			hfile.write("\n")
			if (currentSeconds - lastTime) > 10 :
				lastTime = currentSeconds
				hfile.write("\n")
			outline = ET.SubElement(transcriptoutline, "outline", text=paragraphoutline)



def get_exitcode_stdout_stderr(cmd):
	args = shlex.split(cmd)
	proc = Popen(args, stdout=PIPE, stderr=PIPE)
	out, err = proc.communicate()
	exitcode = proc.returncode
	return exitcode, out, err

#just some feedback while the files are downloading
def reporthook(blocknum, blocksize, totalsize):
	readsofar = blocknum * blocksize
	if totalsize > 0:
		percent = readsofar * 1e2 / totalsize
		s = "\r%5.1f%% %*d / %d" % ( percent, len(str(totalsize)), readsofar, totalsize)
		sys.stderr.write(s)
		if readsofar >= totalsize: # near the end
			sys.stderr.write("\n")
	else: # total size is unknown
		sys.stderr.write("read %d\n" % (readsofar,))

#save the transcript to an xml file. chose xml because we can transcode it to other outputs easily using xslt
def write_transcript_to_opml_file(transcriptoutline, offset, response, episodenumber, hfile, videoid ):

	timeOffset=offset*3600

	hfile.write("<div id=\"player\" name=\"" + videoid+ "\"></div>")
	#hfile.write("https://youtu.be/" + videoid)
	hfile.write("\n\n" )

	for result in response.results:
		alternative = result.alternatives[0]
		#trcrpt = ET.SubElement(show, "transcription", confidence=str(alternative.confidence), rawtext=str(alternative.transcript))
		paragraphoutline = str(alternative.transcript).strip()
		htmlLine = paragraphoutline
		print(u'Transcript: {}'.format(paragraphoutline))
		#print('Confidence: {}'.format(alternative.confidence))
		paragraph = str(alternative.transcript)
		firstdatetime = ""
		for word_info in alternative.words:
			word = str(word_info.word)
			start_time = word_info.start_time
			end_time = word_info.end_time
			
			fullseconds=int(timeOffset + start_time.seconds + start_time.nanos * 1e-9)
			firstdatetime = str(datetime.timedelta(seconds=fullseconds)).replace(":","-")
			if len(firstdatetime) > 0:
				break

		
		if len(firstdatetime) > 0:
			if len(paragraphoutline.split()) > 1:
				(firstword, restword)=paragraphoutline.split(' ', 1)
				youtubetime = firstdatetime.replace("-","h",1)
				youtubetime = youtubetime.replace("-","m",1)
				youtubetime = youtubetime + "s"
				#paragraphoutline = "<a target='naplayer' title='click to play' href='http://naplay.it/" + episodenumber + "/" +firstdatetime + "'>" + firstword + "</a> " + restword ;
				paragraphoutline = "<a target='yt' title='click to play' href='https://youtu.be/" + videoid + "?t=" +youtubetime + "'>" + firstword + "</a> " + restword ;
				htmlLine = "<a title='click 2 play' href=\"javascript:jmpyt('" + videoid + "','" + youtubetime + "');\"  target=\"yt\">" + firstword + "</a> " + restword ;
	
		outline = ET.SubElement(transcriptoutline, "outline", text=paragraphoutline)
		hfile.write(htmlLine)
		hfile.write("\n\n" )
		

#dynamically import the pydub module
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path + "/pydub")
from pydub import AudioSegment
from pydub.utils import make_chunks


#-------start main ----
args = argparser.parse_args()


#-------- download rss feed
urlretrieve(rssfeeduri, "rss.xml", reporthook)
xmldoc = minidom.parse('rss.xml')
itemlist = xmldoc.getElementsByTagName('item')
#------ save the enclosures
rssarray = []
counter = 1
for item in itemlist:
	rssarray.append( {"index": counter, "title": item.getElementsByTagName("title")[0].childNodes[0].data, "url" : item.getElementsByTagName("enclosure")[0].getAttribute('url'), "length": item.getElementsByTagName("enclosure")[0].getAttribute('length') , "image" : item.getElementsByTagName("itunes:image")[0].getAttribute('href')})
	counter = counter + 1

# ------ show the available episodes and ask which one to parse
print(datetime.datetime.utcnow().strftime('%a, %m %b %Y %H:%M:%S GMT'))
print("Available episodes: ")
print("")
for  show in rssarray:
	print( " %02d  - %s " % (show["index"], show["title"]) )

episodenumber = 1
while 1:
	print ("")
	episodenumber = input("Please select the episode number you would like to transcribe now [01]") or "1"

	if int(episodenumber) <= 0 or int(episodenumber) >= counter :
		askcontinue = input("invalid choice. do you want to retry ? (Y/N) [Y]" or "Y" )
		if ( askcontinue == 'n' or askcontinue == "N"):
			sys.exit()
	else:
		break

# determine episode number
url = rssarray[int(episodenumber) - 1]["url"]
image = rssarray[int(episodenumber) -1]["image"]
selectedtitle = rssarray[int(episodenumber) - 1]["title"]
selectedepisodenumber = selectedtitle.split(':')[0]
#pprint( rssarray[int(episodenumber) - 1])
selectedepisodefilesize = int(rssarray[int(episodenumber) - 1]["length"])

#download each episode into its own download directory
downloaddir = dir_path + "/episodes/" + selectedepisodenumber
try:
	os.stat( downloaddir)
except:
	os.mkdir( downloaddir );

print( "selected: " + episodenumber + " now downloading\n\repisode: " + selectedepisodenumber + "\n\rurl    : " + url)

totalFileName = downloaddir + "/" + url.split('/')[-1]
imageFileName = downloaddir + "/coverart.png" 

skipDownload = False
# check if the file already exists
checkfile = Path(totalFileName)
if checkfile.is_file():
	checkfilesize = os.path.getsize(totalFileName)
	if checkfilesize == selectedepisodefilesize :
		skipDownload = True
		print( totalFileName + " is already downloaded.. skipping download")

if not skipDownload:
	urlretrieve(url, totalFileName, reporthook)

print("NO AGENDA EPISODE " +  selectedtitle + "”" )

coverartfilecheck=Path(imageFileName)
if not coverartfilecheck.is_file():
	print("downloading cover art")
	urlretrieve(image, imageFileName, reporthook)
else:
	print("already have coverart .. skipping download ")




#--------------------------

flvfilename=downloaddir + "/" + selectedepisodenumber + ".flv"
opmlfilename = downloaddir + "/" + str(selectedepisodenumber) + "-transcript.opml"
htmlfilename = downloaddir + "/" + str(selectedepisodenumber) + "-transcript.html"

opml = ET.Element("opml")
head = ET.SubElement(opml, "head")
title = ET.SubElement(head, "title").text = selectedtitle
dateCreated = ET.SubElement(head, "dateModified").text = datetime.datetime.utcnow().strftime('%a, %m %b %Y %H:%M:%S GMT')
body = ET.SubElement(opml, "body")
transcriptoutline = ET.SubElement(body, "outline")

htmlfile=open(htmlfilename,"w")


checkflvfile = Path(flvfilename)
if checkflvfile.is_file():
	print("no need to create flv file. already done so")
	videoid = input("what is the youtube id ?")
else:

	print("combining audio and cover art into video file")
	simpleFileName = os.path.splitext(totalFileName)[0]

	cmd = "ffmpeg -r 1 -loop 1 -i " + imageFileName + " -i " + totalFileName + " -acodec copy -r 1 -shortest -vf scale=1280:1280 " + downloaddir + "/" + selectedepisodenumber + ".flv"

	return_code = subprocess.call(cmd, shell=True)

	print("uploading video to youtube")


	strcommand = "youtube-upload --title='No Agenda Episode " + selectedtitle + "' --description='The No Agenda Show. \nEpisode " + selectedepisodenumber + " with Adam Curry and John C. Dvorak. \n http://noagendashow.com '  --category='News & Politics' --playlist='No Agenda' --client-secret=client_secrets.json  " + flvfilename

	exitcode, out, err = get_exitcode_stdout_stderr(strcommand)

	print( "exitcode: " + str(exitcode) + " out: " + out.decode("utf-8") )

	videoid=out.decode("utf-8").strip()

	print("yay:: " + videoid)
	print("waiting 40 minutes before checking for transcript")
	time.sleep(40 * 60)

#--------------------------


if len(videoid) > 0:
	print( "yay:: " + videoid)


	youtube = get_authenticated_service(args)

	while (True):

		try:
			captionId = list_captions(youtube, videoid)
			if (len(captionId) > 0):
				download_caption(youtube, captionId, 'srt', htmlfile)
				break
			else:
				print("waiting another 10 minutes")
				time.sleep(10 * 60)

		except HttpError as e:
			print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
			print("waiting another 40 minutes")
			time.sleep(40 * 60)


else:
	bucket = storage_client.get_bucket(bucket_name)
	fullbucketuri = "gs://" + bucket_name + "/"


	print("splitting mp3 in 1 hour chunks")
	# spilt mp3 into 1 hour chunks
	fullfile = AudioSegment.from_mp3(totalFileName)
	fullfile = fullfile.set_channels(1)
	totalLength = len(fullfile)
	onehours = 3600000

	numberoffullhours = int(totalLength / onehours)
	remainder = totalLength % onehours

	print("totalLength: " + str(int(totalLength/60000)) + " minutes")
	print("numberoffullhours: " + str(numberoffullhours))
	print("remainder: " + str(int(remainder/60000)) + " minutes")



	#split mmp3 into 1 hour chuncs
	chunks = make_chunks(fullfile, onehours)

	for i, chunk in enumerate(chunks):
		chunk_name = simpleFileName + "-{0}.flac".format(i+1)
		filenameext=os.path.basename(chunk_name)
		print ("exporting " , chunk_name)
		chunk.export(chunk_name, format="flac")

		#upload chunk to bucket 
		print("uploading " + filenameext + " to bucket")
		blob = bucket.blob(filenameext)
		blob.upload_from_filename(chunk_name)


		#transcribe chunk
		gcs_uri=fullbucketuri + filenameext

		print("starting transcription for " + filenameext)
		client = speech.SpeechClient()
		audio = speech.types.RecognitionAudio(uri=gcs_uri)
		speechcontext = speech.types.SpeechContext(phrases=commonNoAgendaPhrases)
		config = speech.types.RecognitionConfig(
			language_code='en-US',
			use_enhanced=True,
	        model='phone_call',
	        speech_contexts=[speechcontext],
	        enable_word_time_offsets=True,
			enable_automatic_punctuation=True)

		operation = client.long_running_recognize(config, audio)

		print('Waiting for operation to complete...')
		time.sleep(100)
		response = operation.result(timeout=6000)

		#write transcription for chunk to file
		write_transcript_to_opml_file(transcriptoutline, i, response, selectedepisodenumber, htmlfile, videoid)

		#delete file from bucket after transcode
		blob.delete()



tree = ET.ElementTree(opml)
tree.write(opmlfilename)


htmlfile.close()

print("NO AGENDA EPISODE " +  selectedtitle + "”" )
print(url.split('/')[-1])




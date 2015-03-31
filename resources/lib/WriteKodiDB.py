#################################################################################################
# WriteKodiDB
#################################################################################################


import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import urllib
import sqlite3
import os

from DownloadUtils import DownloadUtils
from PlayUtils import PlayUtils
from CreateFiles import CreateFiles
from ReadKodiDB import ReadKodiDB
from ReadEmbyDB import ReadEmbyDB
from API import API
import Utils as utils

addon = xbmcaddon.Addon(id='plugin.video.emby')
addondir = xbmc.translatePath(addon.getAddonInfo('profile'))
dataPath = os.path.join(addondir,"library")
movieLibrary = os.path.join(dataPath,'movies')
tvLibrary = os.path.join(dataPath,'tvshows')
musicvideoLibrary = os.path.join(dataPath,'musicvideos')

sleepVal = 20

class WriteKodiDB():

    def updatePlayCountFromKodi(self, id, type, playcount=0):
        #when user marks item watched from kodi interface update this in MB3
        xbmc.sleep(sleepVal)
        utils.logMsg("MB3 Sync", "updatePlayCountFromKodi Called")
        
        mb3Id = ReadKodiDB().getEmbyIdByKodiId(id, type)

        if(mb3Id != None):
            addon = xbmcaddon.Addon(id='plugin.video.emby')
            port = addon.getSetting('port')
            host = addon.getSetting('ipaddress')
            server = host + ":" + port        
            downloadUtils = DownloadUtils()
            userid = downloadUtils.getUserId()           
        
            watchedurl = 'http://' + server + '/mediabrowser/Users/' + userid + '/PlayedItems/' + mb3Id
            utils.logMsg("MB3 Sync","watchedurl -->" + watchedurl)
            if playcount != 0:
                downloadUtils.downloadUrl(watchedurl, postBody="", type="POST")
            else:
                downloadUtils.downloadUrl(watchedurl, type="DELETE")
        
    def updateMovieToKodiLibrary_Batched(self, MBitem, KodiItem):
        addon = xbmcaddon.Addon(id='plugin.video.emby')
        port = addon.getSetting('port')
        host = addon.getSetting('ipaddress')
        server = host + ":" + port
        downloadUtils = DownloadUtils()
        userid = downloadUtils.getUserId()
        
        timeInfo = API().getTimeInfo(MBitem)
        userData=API().getUserData(MBitem)
        people = API().getPeople(MBitem)
        genre = API().getGenre(MBitem)
        studios = API().getStudios(MBitem)
        mediaStreams=API().getMediaStreams(MBitem)
        
        thumbPath = API().getArtwork(MBitem, "Primary")
        
        params = list()
        
        self.getArtworkParam_Batched(KodiItem, MBitem, params)
        
        #set Filename
        playurl = PlayUtils().getPlayUrl(server, MBitem["Id"], MBitem)
        docleanup = self.setKodiFilename(KodiItem["movieid"], KodiItem["file"], playurl, "movie")
        #if the path has been set directly in the DB, cleanup the locally created files to import the media-item into the Kodi DB to prevent Kodi from scanning it again.
        if docleanup: 
            itemPath = os.path.join(movieLibrary,MBitem["Id"])
            utils.removeDirectory(os.path.join(movieLibrary,MBitem["Id"] + os.sep))
        
        #update common properties
        duration = (int(timeInfo.get('Duration'))*60)
        self.getPropertyParam_Batched(KodiItem, "runtime", duration, params)
        self.getPropertyParam_Batched(KodiItem, "year", MBitem.get("ProductionYear"), params)
        self.getPropertyParam_Batched(KodiItem, "mpaa", MBitem.get("OfficialRating"), params)
        self.getPropertyParam_Batched(KodiItem, "lastplayed", userData.get("LastPlayedDate"), params)

        self.getPropertyParamArray_Batched(KodiItem, "tag", MBitem.get("Tag"), params)
        
        if MBitem.get("CriticRating") != None:
            self.getPropertyParam_Batched(KodiItem, "rating", int(MBitem.get("CriticRating"))/10, params)

        self.getPropertyParam_Batched(KodiItem, "plotoutline", MBitem.get("ShortOverview"), params)
        self.getPropertyParam_Batched(KodiItem, "set", MBitem.get("TmdbCollectionName"), params)
        self.getPropertyParam_Batched(KodiItem, "sorttitle", MBitem.get("SortName"), params)

        if MBitem.get("ProviderIds") != None:
            if MBitem.get("ProviderIds").get("Imdb") != None:
                self.getPropertyParam_Batched(KodiItem, "imdbnumber", MBitem.get("ProviderIds").get("Imdb"), params)

        # FIXME --> Taglines not returned by MB3 server !?
        if MBitem.get("TagLines") != None:
            self.getPropertyParam_Batched(KodiItem, "tagline", MBitem.get("TagLines")[0], params)      
        
        self.getPropertyParamArray_Batched(KodiItem, "writer", people.get("Writer"), params)
        self.getPropertyParamArray_Batched(KodiItem, "director", people.get("Director"), params)
        self.getPropertyParamArray_Batched(KodiItem, "genre", MBitem.get("Genres"), params)

        if(studios != None):
            for x in range(0, len(studios)):
                studios[x] = studios[x].replace("/", "&")
            self.getPropertyParamArray_Batched(KodiItem, "studio", studios, params)
            
        # FIXME --> ProductionLocations not returned by MB3 server !?
        self.getPropertyParamArray_Batched(KodiItem, "country", MBitem.get("ProductionLocations"), params)

        #trailer link
        trailerUrl = None
        if MBitem.get("LocalTrailerCount") != None and MBitem.get("LocalTrailerCount") > 0:
            itemTrailerUrl = "http://" + server + "/mediabrowser/Users/" + userid + "/Items/" + MBitem.get("Id") + "/LocalTrailers?format=json"
            jsonData = downloadUtils.downloadUrl(itemTrailerUrl, suppress=False, popup=0 )
            if(jsonData != ""):
                trailerItem = json.loads(jsonData)
                if trailerItem[0].get("LocationType") == "FileSystem":
                    trailerUrl = "plugin://plugin.video.emby/?id=" + trailerItem[0].get("Id") + '&mode=play'
                    self.getPropertyParam_Batched(KodiItem, "trailer", trailerUrl, params)
                

        changes = False
        # if there were movies changes then send the update via JSONRPC
        if(len(params) > 0):
            changes |= True
            utils.logMsg("UpdateMovieParams", str(params), level = 2)
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, %s}, "id": 1 }'
            paramString = ""
            paramLen = len(params)
            for x in range(0, paramLen):
                param = params[x]
                paramString += param
                if(x < paramLen-1):
                    paramString += ", "
            jsoncommand = jsoncommand %(KodiItem['movieid'], paramString)
            utils.logMsg("executeJSONRPC : ", jsoncommand, level = 2)
            xbmc.sleep(sleepVal)
            result = xbmc.executeJSONRPC(jsoncommand)
            
        #add actors
        changes |= self.AddActorsToMedia(KodiItem,MBitem.get("People"), "movie")
        
        #add theme music
        if addon.getSetting("syncThemeMusic") == "true":
            CreateFiles().copyThemeMusic(MBitem)
            
        #add extra fanart
        if addon.getSetting("syncExtraFanart") == "true":
           CreateFiles().copyExtraFanart(MBitem)
        
        if(changes):
            utils.logMsg("Updated item to Kodi Library", MBitem["Id"] + " - " + MBitem["Name"], level=0)
            
        return changes
        
    def updateMusicVideoToKodiLibrary_Batched(self, MBitem, KodiItem):
        addon = xbmcaddon.Addon(id='plugin.video.emby')
        port = addon.getSetting('port')
        host = addon.getSetting('ipaddress')
        server = host + ":" + port
        downloadUtils = DownloadUtils()
        userid = downloadUtils.getUserId()
        
        timeInfo = API().getTimeInfo(MBitem)
        userData=API().getUserData(MBitem)
        people = API().getPeople(MBitem)
        genre = API().getGenre(MBitem)
        studios = API().getStudios(MBitem)
        mediaStreams=API().getMediaStreams(MBitem)
        
        thumbPath = API().getArtwork(MBitem, "Primary")
        
        params = list()
        
        self.getArtworkParam_Batched(KodiItem, MBitem, params)

        #update common properties
        duration = (int(timeInfo.get('Duration'))*60)
        self.getPropertyParam_Batched(KodiItem, "runtime", duration, params)
        self.getPropertyParam_Batched(KodiItem, "year", MBitem.get("ProductionYear"), params)
        self.getPropertyParamArray_Batched(KodiItem, "director", people.get("Director"), params)
        self.getPropertyParamArray_Batched(KodiItem, "genre", MBitem.get("Genres"), params)
        self.getPropertyParamArray_Batched(KodiItem, "artist", MBitem.get("Artist"), params)
        self.getPropertyParamArray_Batched(KodiItem, "album", MBitem.get("Album"), params)
        self.getPropertyParam_Batched(KodiItem, "lastplayed", userData.get("LastPlayedDate"), params)

        if(studios != None):
            for x in range(0, len(studios)):
                studios[x] = studios[x].replace("/", "&")
            self.getPropertyParamArray_Batched(KodiItem, "studio", studios, params)

        changes = False
        # if there were movies changes then send the update via JSONRPC
        if(len(params) > 0):
            changes |= True
            utils.logMsg("UpdateMovieParams", str(params), level = 2)
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, %s}, "id": 1 }'
            paramString = ""
            paramLen = len(params)
            for x in range(0, paramLen):
                param = params[x]
                paramString += param
                if(x < paramLen-1):
                    paramString += ", "
            jsoncommand = jsoncommand %(KodiItem['musicvideoid'], paramString)
            utils.logMsg("executeJSONRPC : ", jsoncommand, level = 2)
            xbmc.sleep(sleepVal)
            result = xbmc.executeJSONRPC(jsoncommand)
        
        CreateFiles().createSTRM(MBitem)
        CreateFiles().createNFO(MBitem)
        
        if(changes):
            utils.logMsg("Updated musicvideo to Kodi Library", MBitem["Id"] + " - " + MBitem["Name"], level=0)
            
    def updateMovieToKodiLibrary(self, MBitem, KodiItem):
        
        addon = xbmcaddon.Addon(id='plugin.video.emby')
        port = addon.getSetting('port')
        host = addon.getSetting('ipaddress')
        server = host + ":" + port        
        downloadUtils = DownloadUtils()
        userid = downloadUtils.getUserId()
        
        timeInfo = API().getTimeInfo(MBitem)
        userData=API().getUserData(MBitem)
        people = API().getPeople(MBitem)
        genre = API().getGenre(MBitem)
        studios = API().getStudios(MBitem)
        mediaStreams=API().getMediaStreams(MBitem)
        
        thumbPath = API().getArtwork(MBitem, "Primary")
        
        changes = False
        
        #update/check all artwork
        changes |= self.updateArtWork(KodiItem,MBitem)

        #update common properties
        duration = (int(timeInfo.get('Duration'))*60)
        changes |= self.updateProperty(KodiItem,"runtime",duration,"movie")
        changes |= self.updateProperty(KodiItem,"year",MBitem.get("ProductionYear"),"movie")
        changes |= self.updateProperty(KodiItem,"mpaa",MBitem.get("OfficialRating"),"movie")
        changes |= self.updateProperty(KodiItem,"lastplayed",MBitem.get("LastPlayedDate"),"movie")
        changes |= self.updatePropertyArray(KodiItem,"tag",MBitem.get("Tag"),"movie")
        
        if MBitem.get("CriticRating") != None:
            changes |= self.updateProperty(KodiItem,"rating",int(MBitem.get("CriticRating"))/10,"movie")

        changes |= self.updateProperty(KodiItem,"plotoutline",MBitem.get("ShortOverview"),"movie")
        changes |= self.updateProperty(KodiItem,"set",MBitem.get("TmdbCollectionName"),"movie")
        changes |= self.updateProperty(KodiItem,"sorttitle",MBitem.get("SortName"),"movie")

        if MBitem.get("ProviderIds") != None:
            if MBitem.get("ProviderIds").get("Imdb") != None:
                changes |= self.updateProperty(KodiItem,"imdbnumber",MBitem.get("ProviderIds").get("Imdb"),"movie")

        # FIXME --> Taglines not returned by MB3 server !?
        if MBitem.get("TagLines") != None:
            changes |= self.updateProperty(KodiItem,"tagline",MBitem.get("TagLines")[0],"movie")      
        
        changes |= self.updatePropertyArray(KodiItem,"writer",people.get("Writer"),"movie")
        changes |= self.updatePropertyArray(KodiItem,"director",people.get("Director"),"movie")
        changes |= self.updatePropertyArray(KodiItem,"genre",MBitem.get("Genres"),"movie")

        if(studios != None):
            for x in range(0, len(studios)):
                studios[x] = studios[x].replace("/", "&")
            changes |= self.updatePropertyArray(KodiItem,"studio",studios,"movie")
            
        # FIXME --> ProductionLocations not returned by MB3 server !?
        changes |= self.updatePropertyArray(KodiItem,"country",MBitem.get("ProductionLocations"),"movie")

        #trailer link
        trailerUrl = None
        if MBitem.get("LocalTrailerCount") != None and MBitem.get("LocalTrailerCount") > 0:
            itemTrailerUrl = "http://" + server + "/mediabrowser/Users/" + userid + "/Items/" + MBitem.get("Id") + "/LocalTrailers?format=json"
            jsonData = downloadUtils.downloadUrl(itemTrailerUrl, suppress=False, popup=0 )
            if(jsonData != ""):
                trailerItem = json.loads(jsonData)
                trailerUrl = "plugin://plugin.video.emby/?id=" + trailerItem[0].get("Id") + '&mode=play'
                changes |= self.updateProperty(KodiItem,"trailer",trailerUrl,"movie")

        #add actors
        changes |= self.AddActorsToMedia(KodiItem,MBitem.get("People"),"movie")
        
        #set Filename
        playurl = PlayUtils().getPlayUrl(server, MBitem["Id"], MBitem)
        self.setKodiFilename(KodiItem["movieid"], KodiItem["file"], playurl, "movie")
        
        
        #add theme music
        if addon.getSetting("syncThemeMusic") == "true":
            CreateFiles().copyThemeMusic(MBitem)
            
        #add extra fanart
        if addon.getSetting("syncExtraFanart") == "true":
           CreateFiles().copyExtraFanart(MBitem)
        
        if changes:
            utils.logMsg("Updated item to Kodi Library", MBitem["Id"] + " - " + MBitem["Name"])
        
    def updateTVShowToKodiLibrary( self, MBitem, KodiItem ):
        
        addon = xbmcaddon.Addon(id='plugin.video.emby')
        port = addon.getSetting('port')
        host = addon.getSetting('ipaddress')
        server = host + ":" + port        
        downloadUtils = DownloadUtils()
        
        timeInfo = API().getTimeInfo(MBitem)
        userData=API().getUserData(MBitem)
        people = API().getPeople(MBitem)
        genre = API().getGenre(MBitem)
        studios = API().getStudios(MBitem)
        mediaStreams=API().getMediaStreams(MBitem)
        
        thumbPath = API().getArtwork(MBitem, "Primary")
        
        changes = False
        
        #set Filename
        playurl = PlayUtils().getPlayUrl(server, MBitem["Id"], MBitem)
        #make sure that the path always ends with a slash
        playurl = playurl + "/"
        docleanup = self.setKodiFilename(KodiItem["tvshowid"], KodiItem["file"], playurl, "tvshow")
        
        #if the path has been set directly in the DB, cleanup the locally created nfo file to import the tvshow into the Kodi DB to prevent Kodi from scanning it again.
        if docleanup: 
            nfoPath = os.path.join(tvLibrary,MBitem["Id"],"tvshow.nfo")
            print "about to delete file--> " + nfoPath
            os.remove(nfoPath)
        
        #update/check all artwork
        changes |= self.updateArtWork(KodiItem,MBitem)
        
        #update common properties
        if MBitem.get("PremiereDate") != None:
            premieredatelist = (MBitem.get("PremiereDate")).split("T")
            premieredate = premieredatelist[0]
            changes |= self.updateProperty(KodiItem,"premiered",premieredate,"tvshow")
        
        changes |= self.updateProperty(KodiItem,"mpaa",MBitem.get("OfficialRating"),"tvshow")
        changes |= self.updateProperty(KodiItem,"lastplayed",MBitem.get("LastPlayedDate"),"tvshow")
        
        if MBitem.get("CriticRating") != None:
            changes |= self.updateProperty(KodiItem,"rating",int(MBitem.get("CriticRating"))/10,"tvshow")
        
        changes |= self.updateProperty(KodiItem,"sorttitle",MBitem.get("SortName"),"tvshow")
        
        if MBitem.get("ProviderIds") != None:
            if MBitem.get("ProviderIds").get("Imdb") != None:
                changes |= self.updateProperty(KodiItem,"imdbnumber",MBitem.get("ProviderIds").get("Imdb"),"tvshow")
        
        changes |= self.updatePropertyArray(KodiItem,"genre",MBitem.get("Genres"),"tvshow")
        
        if(studios != None):
            for x in range(0, len(studios)):
                studios[x] = studios[x].replace("/", "&")
            changes |= self.updatePropertyArray(KodiItem,"studio",studios,"tvshow")
        
        # FIXME --> ProductionLocations not returned by MB3 server !?
        changes |= self.updatePropertyArray(KodiItem,"country",MBitem.get("ProductionLocations"),"tvshow")
        
        #add actors
        changes |= self.AddActorsToMedia(KodiItem,MBitem.get("People"),"tvshow")
        
        #update season artwork
        self.updateSeasonArtwork(MBitem, KodiItem)
        
        CreateFiles().createNFO(MBitem)
        
        #add theme music
        if addon.getSetting("syncThemeMusic") == "true":
            CreateFiles().copyThemeMusic(MBitem)
        
        #add extra fanart
        if addon.getSetting("syncExtraFanart") == "true":
           CreateFiles().copyExtraFanart(MBitem)
        
        if changes:
            utils.logMsg("Updated item to Kodi Library", MBitem["Id"] + " - " + MBitem["Name"])
            
        return changes
                  
    def updateEpisodeToKodiLibrary( self, MBitem, KodiItem ):
        
        addon = xbmcaddon.Addon(id='plugin.video.emby')
        port = addon.getSetting('port')
        host = addon.getSetting('ipaddress')
        server = host + ":" + port        
        downloadUtils = DownloadUtils()
        userid = downloadUtils.getUserId()
        
        timeInfo = API().getTimeInfo(MBitem)
        people = API().getPeople(MBitem)
        genre = API().getGenre(MBitem)
        studios = API().getStudios(MBitem)
        mediaStreams=API().getMediaStreams(MBitem)
        userData=API().getUserData(MBitem)
        
        thumbPath = API().getArtwork(MBitem, "Primary")
        
        changes = False

        #update/check all artwork
        changes |= self.updateArtWork(KodiItem,MBitem)
        
        #set Filename (also submit strmfilepath to rename that if path has changed to original location)
        playurl = PlayUtils().getPlayUrl(server, MBitem["Id"], MBitem)
        docleanup = self.setKodiFilename(KodiItem["episodeid"], KodiItem["file"], playurl, "episode")
        
        #if the path has been set directly in the DB, cleanup the locally created files to import the media-item into the Kodi DB to prevent Kodi from scanning it again.
        if docleanup: 
            path = os.path.join(tvLibrary,MBitem["SeriesId"] + os.sep)
            if xbmcvfs.exists(path):
                allDirs, allFiles = xbmcvfs.listdir(path)
                for file in allFiles:
                    if MBitem["Id"] in file:
                        xbmcvfs.delete(os.path.join(path,file))

        #update common properties
        duration = (int(timeInfo.get('Duration'))*60)
        changes |= self.updateProperty(KodiItem,"runtime",duration,"episode")
        changes |= self.updateProperty(KodiItem,"lastplayed",userData.get("LastPlayedDate"),"episode")

        if MBitem.get("PremiereDate") != None:
            premieredatelist = (MBitem.get("PremiereDate")).split("T")
            premieredate = premieredatelist[0]
            premieretime = premieredatelist[1].split(".")[0]
            firstaired = premieredate + " " + premieretime
            # for Helix we use the whole time string, for kodi 15 we have to change to only the datestring
            # see: http://forum.kodi.tv/showthread.php?tid=218743
            if KodiItem["firstaired"] != premieredate:
                self.updateProperty(KodiItem,"firstaired",firstaired,"episode")
        
        if MBitem.get("CriticRating") != None:
            changes |= self.updateProperty(KodiItem,"rating",int(MBitem.get("CriticRating"))/10,"episode")

        changes |= self.updatePropertyArray(KodiItem,"writer",people.get("Writer"),"episode")

        #add actors
        changes |= self.AddActorsToMedia(KodiItem,MBitem.get("People"),"episode")
        
        if changes:
            utils.logMsg("Updated item to Kodi Library", MBitem["Id"] + " - " + MBitem["Name"])
    
        return changes
        
    def getArtworkParam_Batched(self, KodiItem, MBitem, params):

        '''
        item_type=str(MBitem.get("Type"))
        if item_type == "Series":
            id = KodiItem['tvshowid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "art": %s}, "id": 1 }'
        elif item_type == "Episode":
            # episodes don't have any artwork - they derrive this from the tv show
            return False
        elif item_type == "MusicVideo":
            id = KodiItem['musicvideoid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { musicvideoid": %i, "art": %s}, "id": 1 }'
        elif item_type == "Movie":
            id = KodiItem['movieid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "art": %s}, "id": 1 }'
        '''
        
        #update artwork
        changes = False
        
        artwork = {}
        artwork["poster"] = API().getArtwork(MBitem, "Primary")
        artwork["banner"] = API().getArtwork(MBitem, "Banner")
        artwork["clearlogo"] = API().getArtwork(MBitem, "Logo")
        artwork["clearart"] = API().getArtwork(MBitem, "Art")
        artwork["landscape"] = API().getArtwork(MBitem, "Thumb")
        artwork["discart"] = API().getArtwork(MBitem, "Disc")
        artwork["fanart"] = API().getArtwork(MBitem, "Backdrop")
        
        for art in artwork:
            if artwork.get(art) != "":
                if KodiItem["art"].has_key(art):
                    curValue = urllib.unquote(KodiItem['art'][art]).decode('utf8')
                    if not artwork.get(art) in curValue:
                        KodiItem["art"][art] = artwork.get(art)
                        changes = True
                else:
                    KodiItem["art"][art] = artwork.get(art)
                    changes = True
        
        if len(KodiItem["art"]) == 0:
            changes = False
        
        if changes:
            json_array = json.dumps(KodiItem["art"])
            params.append("\"art\": " + json_array)
            #result = xbmc.executeJSONRPC(jsoncommand %(id, json_array))
        return changes
        
    # adds or updates artwork to the given Kodi file in database
    def updateArtWork(self,KodiItem,MBitem):
        
        item_type=str(MBitem.get("Type"))
        
        if item_type == "Series":
            id = KodiItem['tvshowid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "art": %s}, "id": 1 }'
        elif item_type == "Episode":
            # episodes don't have any artwork - they derrive this from the tv show
            return False
        elif item_type == "MusicVideo":
            id = KodiItem['musicvideoid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { musicvideoid": %i, "art": %s}, "id": 1 }'
        elif item_type == "Movie":
            id = KodiItem['movieid']
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "art": %s}, "id": 1 }'

        #update artwork
        changes = False
        
        artwork = {}
        artwork["poster"] = API().getArtwork(MBitem, "Primary")
        artwork["banner"] = API().getArtwork(MBitem, "Banner")
        artwork["clearlogo"] = API().getArtwork(MBitem, "Logo")
        artwork["clearart"] = API().getArtwork(MBitem, "Art")
        artwork["landscape"] = API().getArtwork(MBitem, "Thumb")
        artwork["discart"] = API().getArtwork(MBitem, "Disc")
        artwork["fanart"] = API().getArtwork(MBitem, "Backdrop")
        
        for art in artwork:
            if artwork.get(art) != "":
                if KodiItem["art"].has_key(art):
                    curValue = urllib.unquote(KodiItem['art'][art]).decode('utf8')
                    if not artwork.get(art) in curValue:
                        KodiItem["art"][art] = artwork.get(art)
                        changes = True
                else:
                    KodiItem["art"][art] = artwork.get(art)
                    changes = True
        
        if len(KodiItem["art"]) == 0:
            changes = False
        
        if changes:
            json_array = json.dumps(KodiItem["art"])
            result = xbmc.executeJSONRPC(jsoncommand %(id, json_array))
        return changes
    
    def getPropertyParam_Batched(self,KodiItem, propertyName, propertyValue, params, forced = False):
    
        '''
        if fileType == "tvshow":
            id = KodiItem['tvshowid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "episode":
            id = KodiItem['episodeid']  
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": %i}, "id": 1 }'            
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "musicvideo":
            id = KodiItem['musicvideoid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "movie":
            id = KodiItem['movieid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": "%s"}, "id": 1 }'
        '''
        
        changes = False
        if ((propertyValue != KodiItem[propertyName]) or forced):
            if propertyValue != None:
                if type(propertyValue) is int:
                    #xbmc.sleep(sleepVal)
                    utils.logMsg("MB3 Sync","updating property..." + str(propertyName))
                    utils.logMsg("MB3 Sync","kodi value:" + str(KodiItem[propertyName]) + " MB value: " + str(propertyValue))
                    params.append("\"" + propertyName + "\": " + str(propertyValue))
                    #xbmc.executeJSONRPC(jsoncommand_i %(id, propertyName, propertyValue))
                    changes = True
                else:
                    #xbmc.sleep(sleepVal)
                    utils.logMsg("MB3 Sync","updating property..." + str(propertyName))
                    utils.logMsg("MB3 Sync","kodi value:" + KodiItem[propertyName] + " MB value: " + propertyValue)
                    params.append("\"" + propertyName + "\": \"" + str(propertyValue) + "\"")
                    #xbmc.executeJSONRPC(jsoncommand_s %(id, propertyName, propertyValue.encode('utf-8')))
                    changes = True
                    
        return changes
        
    # adds or updates the given property on the videofile in Kodi database
    def updateProperty(self,KodiItem,propertyName,propertyValue,fileType,forced=False):
        if fileType == "tvshow":
            id = KodiItem['tvshowid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "episode":
            id = KodiItem['episodeid']  
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": %i}, "id": 1 }'            
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "musicvideo":
            id = KodiItem['musicvideoid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": "%s"}, "id": 1 }'
        elif fileType == "movie":
            id = KodiItem['movieid']
            jsoncommand_i = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": %i}, "id": 1 }'
            jsoncommand_s = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": "%s"}, "id": 1 }'
        
        changes = False
        if ((propertyValue != KodiItem[propertyName]) or forced):
            if propertyValue != None:
                if type(propertyValue) is int:
                    xbmc.sleep(sleepVal)
                    utils.logMsg("MB3 Sync","updating property..." + str(propertyName))
                    utils.logMsg("MB3 Sync","kodi value:" + str(KodiItem[propertyName]) + " MB value: " + str(propertyValue))
                    xbmc.executeJSONRPC(jsoncommand_i %(id, propertyName, propertyValue))
                    changes = True
                else:
                    xbmc.sleep(sleepVal)
                    utils.logMsg("MB3 Sync","updating property..." + str(propertyName))
                    utils.logMsg("MB3 Sync","kodi value:" + KodiItem[propertyName] + " MB value: " + propertyValue)
                    xbmc.executeJSONRPC(jsoncommand_s %(id, propertyName, propertyValue.encode('utf-8')))
                    changes = True
                    
        return changes

    def getPropertyParamArray_Batched(self, KodiItem, propertyName, propertyCollection, params):
        '''
        if fileType == "tvshow":
            id = KodiItem['tvshowid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "episode":
            id = KodiItem['episodeid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "musicvideo":
            id = KodiItem['musicvideoid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "movie":
            id = KodiItem['movieid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": %s}, "id": 1 }'
        '''
        
        pendingChanges = False
        if propertyCollection != None:   
            currentvalues = set(KodiItem[propertyName])
            for item in propertyCollection:
                if not item in currentvalues:
                    pendingChanges = True
                    json_array = json.dumps(propertyCollection)
            
            if pendingChanges:
                #xbmc.sleep(sleepVal)
                utils.logMsg("MB3 Sync","updating propertyarray... Name:" + str(propertyName) + " Current:" + str(currentvalues) + " New:" + str(json_array))
                params.append("\"" + propertyName + "\": " + json_array)
                #xbmc.executeJSONRPC(jsoncommand %(id,propertyName,json_array))

        return pendingChanges        
        
    # adds or updates the property-array on the videofile in Kodi database
    def updatePropertyArray(self,KodiItem,propertyName,propertyCollection,fileType):
        if fileType == "tvshow":
            id = KodiItem['tvshowid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetTVShowDetails", "params": { "tvshowid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "episode":
            id = KodiItem['episodeid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": { "episodeid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "musicvideo":
            id = KodiItem['musicvideoid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMusicVideoDetails", "params": { "musicvideoid": %i, "%s": %s}, "id": 1 }'
        elif fileType == "movie":
            id = KodiItem['movieid']   
            jsoncommand = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": { "movieid": %i, "%s": %s}, "id": 1 }'

        pendingChanges = False
        if propertyCollection != None:   
            currentvalues = set(KodiItem[propertyName])
            for item in propertyCollection:
                if not item in currentvalues:
                    pendingChanges = True
                    json_array = json.dumps(propertyCollection)
            
            if pendingChanges:
                xbmc.sleep(sleepVal)
                utils.logMsg("MB3 Sync","updating propertyarray... Name:" + str(propertyName) + " Current:" + str(currentvalues) + " New:" + str(json_array))
                xbmc.executeJSONRPC(jsoncommand %(id,propertyName,json_array))

        return pendingChanges
    
    def addMovieToKodiLibrary( self, item ):
        itemPath = os.path.join(movieLibrary,item["Id"])
        strmFile = os.path.join(itemPath,item["Id"] + ".strm")
        
        changes = False
        
        #create path if not exists
        if not xbmcvfs.exists(itemPath + os.sep):
            xbmcvfs.mkdir(itemPath)
        
        #create nfo file
        changes = CreateFiles().createNFO(item)
        
        # create strm file
        changes |= CreateFiles().createSTRM(item)
        
        if changes:
            utils.logMsg("MB3 Sync","Added movie to Kodi Library",item["Id"] + " - " + item["Name"])
    
    def addMusicVideoToKodiLibrary( self, item ):
        itemPath = os.path.join(musicvideoLibrary,item["Id"])
        strmFile = os.path.join(itemPath,item["Id"] + ".strm")
        
        changes = False
        
        #create path if not exists
        if not xbmcvfs.exists(itemPath + os.sep):
            xbmcvfs.mkdir(itemPath)
        
        #create nfo file
        changes = CreateFiles().createNFO(item)
        
        # create strm file
        changes |= CreateFiles().createSTRM(item)
        
        if changes:
            utils.logMsg("MB3 Sync","Added musicvideo to Kodi Library",item["Id"] + " - " + item["Name"])
    
    def addEpisodeToKodiLibrary(self, item):
        
        changes = False

        #create nfo file
        changes = CreateFiles().createNFO(item)
        
        # create strm file
        changes |= CreateFiles().createSTRM(item)
        
        if changes:
            utils.logMsg("MB3 Sync","Added episode to Kodi Library",item["Id"] + " - " + item["Name"])
    
    def deleteMovieFromKodiLibrary(self, id ):
        kodiItem = ReadKodiDB().getKodiMovie(id)
        utils.logMsg("deleting movie from Kodi library",id)
        if kodiItem != None:
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.RemoveMovie", "params": { "movieid": %i}, "id": 1 }' %(kodiItem["movieid"]))
        
        path = os.path.join(movieLibrary,id + os.sep)
        utils.removeDirectory(path)
 
    
    def deleteMusicVideoFromKodiLibrary(self, id ):
        utils.logMsg("deleting musicvideo from Kodi library",id)
        kodiItem = ReadKodiDB().getKodiMusicVideo(id)
        if kodiItem != None:
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.RemoveMusicVideo", "params": { "musicvideoid": %i}, "id": 1 }' %(kodiItem["musicvideoid"]))
        
        path = os.path.join(musicvideoLibrary,id)
        allDirs, allFiles = xbmcvfs.listdir(path)
        for dir in allDirs:
            xbmcvfs.rmdir(os.path.join(path,dir))
        for file in allFiles:
            xbmcvfs.delete(os.path.join(path,file))
        xbmcvfs.rmdir(path)   
         
    def deleteEpisodeFromKodiLibrary(self, episodeid, tvshowid ):
        utils.logMsg("deleting episode from Kodi library",episodeid)
        episode = ReadKodiDB().getKodiEpisodeByMbItem(episodeid, tvshowid)
        if episode != None:
            WINDOW = xbmcgui.Window( 10000 )
            WINDOW.setProperty("suspendDeletes", "True")                
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.RemoveEpisode", "params": { "episodeid": %i}, "id": 1 }' %(episode["episodeid"]))
            
            itemPath = os.path.join(tvLibrary,tvshowid)
            allDirs, allFiles = xbmcvfs.listdir(itemPath)
            for file in allFiles:
                if episodeid in file:
                    xbmcvfs.delete(file)
            
            while WINDOW.getProperty("suspendDeletes") == "True":
                xbmc.sleep(100)
            utils.logMsg("episode deleted succesfully!",episodeid)
        else:
            utils.logMsg("episode not found in kodi DB",episodeid)        
            
    def addTVShowToKodiLibrary( self, item ):
        itemPath = os.path.join(tvLibrary,item["Id"])
        
        changes = False
        
        #create path if not exists
        if not xbmcvfs.exists(itemPath + os.sep):
            xbmcvfs.mkdir(itemPath)
            
        #create nfo file
        changes = CreateFiles().createNFO(item)
        
        if changes:
            utils.logMsg("Added TV Show to Kodi Library ",item["Id"] + " - " + item["Name"])
        
    def deleteTVShowFromKodiLibrary(self, id ):
        xbmc.sleep(sleepVal)
        kodiItem = ReadKodiDB().getKodiTVShow(id)
        utils.logMsg("deleting tvshow from Kodi library",id)
 
        if kodiItem != None:
            xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.RemoveTVShow", "params": { "tvshowid": %i}, "id": 1 }' %(kodiItem["tvshowid"]))
        
        path = os.path.join(tvLibrary,id + os.sep)
        utils.removeDirectory(path)

    
    def updateSeasonArtwork(self,MBitem, KodiItem):
        #use sqlite to set the season artwork because no method in API available for this
        #season poster and banner are set by the nfo. landscape image is filled by this method
        #if wanted this feature can be extended to also update the other artwork
        tvshowid = KodiItem["tvshowid"]

        connection = utils.KodiSQL()
        cursor = connection.cursor( )
        
        seasonData = ReadEmbyDB().getTVShowSeasons(MBitem["Id"])
        if seasonData != None:
            for season in seasonData:
                if season.has_key("IndexNumber"):
                    MB3landscape = API().getArtwork(season, "Thumb")
                    if MB3landscape != "":
                        cursor.execute("SELECT idSeason as seasonid FROM seasons WHERE idShow = ? and season = ?",(tvshowid,season["IndexNumber"]))
                        result = cursor.fetchone()
                        if result != None:
                            seasonid = result[0]
                            cursor.execute("SELECT art_id as art_id FROM art WHERE media_id = ? and media_type = ? and type = ?",(seasonid,"season","landscape"))
                            result = cursor.fetchone()
                            if result == None:
                                sql="INSERT into art(media_id, media_type, type, url) values(?, ?, ?, ?)"
                                cursor.execute(sql, (seasonid,"season","landscape",MB3landscape))

        connection.commit()
        cursor.close()   
    
    def setKodiResumePoint(self, id, resume_seconds, total_seconds, fileType):
        #use sqlite to set the resume point while json api doesn't support this yet
        #todo --> submit PR to kodi team to get this added to the jsonrpc api
        
        utils.logMsg("MB3 Sync","setting resume point in kodi db..." + fileType + ": " + str(id))
        xbmc.sleep(sleepVal)
        connection = utils.KodiSQL()
        cursor = connection.cursor( )
        
        if fileType == "episode":
            cursor.execute("SELECT idFile as fileidid FROM episode WHERE idEpisode = ?",(id,))
            result = cursor.fetchone()
            fileid = result[0]
        if fileType == "movie":
            cursor.execute("SELECT idFile as fileidid FROM movie WHERE idMovie = ?",(id,))
            result = cursor.fetchone()
            fileid = result[0]       
        
        cursor.execute("delete FROM bookmark WHERE idFile = ?", (fileid,))
        cursor.execute("select coalesce(max(idBookmark),0) as bookmarkId from bookmark")
        bookmarkId =  cursor.fetchone()[0]
        bookmarkId = bookmarkId + 1
        bookmarksql="insert into bookmark(idBookmark, idFile, timeInSeconds, totalTimeInSeconds, thumbNailImage, player, playerState, type) values(?, ?, ?, ?, ?, ?, ?, ?)"
        cursor.execute(bookmarksql, (bookmarkId,fileid,resume_seconds,total_seconds,None,"DVDPlayer",None,1))
        connection.commit()
        cursor.close()
    
    def setKodiFilename(self, id, oldFileName, newFileName, fileType):
        #use sqlite to set the filename in DB -- needed to avoid problems with resumepoints etc
        #return True if any action is performed, False if no action is performed
        #todo --> submit PR to kodi team to get this added to the jsonrpc api
        #todo --> extend support for musicvideos
        
        actionPerformed = False
        
        oldFileName = utils.convertEncoding(oldFileName)
        newFileName = utils.convertEncoding(newFileName)
        
        # only perform changes if the path actually differs
        if oldFileName != newFileName:
        
            xbmc.sleep(sleepVal)
            connection = utils.KodiSQL()
            cursor = connection.cursor( )
            utils.logMsg("MB3 Sync","setting filename in kodi db..." + fileType + ": " + str(id))
            utils.logMsg("MB3 Sync","old filename -->" + oldFileName)
            utils.logMsg("MB3 Sync","new filename -->" + newFileName)
            
            if fileType == "tvshow" and not newFileName.startswith("http"):
                #for tvshows we only store the path in DB
                cursor.execute("SELECT idPath as pathid FROM tvshowlinkpath WHERE idShow = ?",(id,))
                result = cursor.fetchone()
                pathid = result[0]
                cursor.execute("UPDATE path SET strPath = ?, noUpdate = ?, idParentPath = ? WHERE idPath = ?", (newFileName,1,None,pathid))
            
            else:
                # we need to store both the path and the filename seperately in the kodi db so we split them up
                if "\\" in newFileName:
                    filename = newFileName.rsplit("\\",1)[-1]
                    path = newFileName.replace(filename,"")
                elif "/" in newFileName:
                    filename = newFileName.rsplit("/",1)[-1]
                    path = newFileName.replace(filename,"")
                
                #if we want to use transcoding/play from stream we pass on the complete http path
                #in this case both the path and filename are set to the addonpath
                if newFileName.startswith("http"):
                    path = newFileName
                
                ######### PROCESS EPISODE ############
                if fileType == "episode":
                    
                    #create the path - return id if already exists  
                    cursor.execute("SELECT idPath as pathid FROM path WHERE strPath = ?",(path,))
                    result = cursor.fetchone()
                    if result != None:
                        pathid = result[0]
                    if result == None:
                        cursor.execute("select coalesce(max(idPath),0) as pathid from path")
                        pathid = cursor.fetchone()[0]
                        pathid = pathid + 1
                        pathsql="insert into path(idPath, strPath, strContent, strScraper, noUpdate) values(?, ?, ?, ?, ?)"
                        cursor.execute(pathsql, (pathid,path,None,None,1))
                        
                    #get the file and the current path id
                    cursor.execute("SELECT idFile as fileid FROM episode WHERE idEpisode = ?",(id,))
                    result = cursor.fetchone()
                    fileid = result[0]
                    cursor.execute("SELECT idPath as curpathid FROM files WHERE idFile = ?",(fileid,))
                    result = cursor.fetchone()
                    curpathid = result[0]
                    
                    #remove the old path if different
                    if curpathid != pathid:
                        cursor.execute("DELETE FROM path WHERE idPath = ?",(curpathid,))
                        
                    #set the new path and filename to the episode
                    cursor.execute("UPDATE files SET idPath = ?, strFilename = ? WHERE idFile = ?", (pathid,filename,fileid))

                    
                ######### PROCESS MOVIE ############
                if fileType == "movie":
                    cursor.execute("SELECT idFile as fileid FROM movie WHERE idMovie = ?",(id,))
                    result = cursor.fetchone()
                    fileid = result[0]
                    #write the new filename to the DB
                    cursor.execute("UPDATE files SET strFilename = ? WHERE idFile = ?", (filename,fileid))
                    #set the new path
                    cursor.execute("SELECT idPath as pathid FROM files WHERE idFile = ?",(fileid,))
                    result = cursor.fetchone()
                    pathid = result[0]
                    cursor.execute("UPDATE path SET strPath = ?, strContent = ?, strScraper = ?, noUpdate = ?, idParentPath = ? WHERE idPath = ?", (path, "movies", "metadata.local", 1, None, pathid))               
                
            try:
                connection.commit()
                actionPerformed = True
            except:
                utils.logMsg("MB3 Sync","Error setting filename in kodi db for: " + fileType + ": " + str(id))
                actionPerformed = False
            finally:
                cursor.close()
            
        return actionPerformed

    
    def AddActorsToMedia(self, KodiItem, people, mediatype):
        #use sqlite to set add the actors while json api doesn't support this yet
        #todo --> submit PR to kodi team to get this added to the jsonrpc api
        
        downloadUtils = DownloadUtils()
        if mediatype == "movie":
            id = KodiItem["movieid"]
        if mediatype == "tvshow":
            id = KodiItem["tvshowid"]
        if mediatype == "episode":
            id = KodiItem["episodeid"]

        currentcast = list()
        if KodiItem["cast"] != None:
            for cast in KodiItem["cast"]:
                currentcast.append(cast["name"])
        
        needsUpdate = False
        if(people != None):
            for person in people:              
                if(person.get("Type") == "Actor"):
                    if person.get("Name") not in currentcast:
                        needsUpdate = True
                        break
        
        if(needsUpdate == False):
            return False
        
        utils.logMsg("AddActorsToMedia", "List needs updating")
        
        xbmc.sleep(sleepVal)
        connection = utils.KodiSQL()
        cursor = connection.cursor()
        
        if(people != None):
            for person in people:              
                if(person.get("Type") == "Actor"):
                    if person.get("Name") not in currentcast:
                        utils.logMsg("AddActorsToMedia", "Processing : " + person.get("Name"))
                        Name = person.get("Name")
                        Role = person.get("Role")
                        actorid = None
                        Thumb = downloadUtils.imageUrl(person.get("Id"), "Primary", 0, 400, 400)
                        cursor.execute("SELECT idActor as actorid FROM actors WHERE strActor = ?",(Name,))
                        result = cursor.fetchone()
                        if result != None:
                            actorid = result[0]
                        if actorid == None:
                            cursor.execute("select coalesce(max(idActor),0) as actorid from actors")
                            actorid = cursor.fetchone()[0]
                            actorid = actorid + 1
                            peoplesql="insert into actors(idActor, strActor, strThumb) values(?, ?, ?)"
                            cursor.execute(peoplesql, (actorid,Name,Thumb))
                        
                        if mediatype == "movie":
                            peoplesql="INSERT OR REPLACE into actorlinkmovie(idActor, idMovie, strRole, iOrder) values(?, ?, ?, ?)"
                        if mediatype == "tvshow":
                            peoplesql="INSERT OR REPLACE into actorlinktvshow(idActor, idShow, strRole, iOrder) values(?, ?, ?, ?)"
                        if mediatype == "episode":
                            peoplesql="INSERT OR REPLACE into actorlinkepisode(idActor, idEpisode, strRole, iOrder) values(?, ?, ?, ?)"
                        cursor.execute(peoplesql, (actorid,id,Role,None))
        
        connection.commit()
        cursor.close()
        
        return True
    
    def addBoxsetToKodiLibrary(self, boxset):
        #use sqlite to set add the set 
        connection = utils.KodiSQL()
        cursor = connection.cursor() 
        
        strSet = boxset["Name"]
        # check if exists
        cursor.execute("SELECT idSet FROM sets WHERE strSet = ?", (strSet,))
        result = cursor.fetchone()
        setid = None
        if result != None:
            setid = result[0]
            currentsetartsql =  "SELECT type, url FROM art where media_type = ? and media_id = ? and url != ''"
            cursor.execute(currentsetartsql, ("set", setid))
            existing_type_map = {}
            rows = cursor.fetchall()
            for row in rows:
                existing_type_map[row[0] ] = row[1]
          
            artwork = {}
            artwork["poster"] = API().getArtwork(boxset, "Primary")
            artwork["banner"] = API().getArtwork(boxset, "Banner")
            artwork["clearlogo"] = API().getArtwork(boxset, "Logo")
            artwork["clearart"] = API().getArtwork(boxset, "Art")
            artwork["landscape"] = API().getArtwork(boxset, "Thumb")
            artwork["discart"] = API().getArtwork(boxset, "Disc")
            artwork["fanart"] = API().getArtwork(boxset, "Backdrop")
           
            art_types = ['poster','fanart','landscape','clearlogo','clearart','banner','discart']
            for update_type in art_types:
                if ( update_type in existing_type_map ):
                    if ( existing_type_map[update_type] != artwork[update_type] ) and artwork[update_type] != '':
                        setupdateartsql = "UPDATE art SET url = ? where media_type = ? and media_id = ? and type = ?"
                        cursor.execute(setupdateartsql,(artwork[update_type],"set",setid,update_type))
                elif artwork[update_type] != '':
                    setartsql = "INSERT INTO art(media_id, media_type, type, url) VALUES(?,?,?,?)"
                    cursor.execute(setartsql,(setid,"set",update_type,artwork[update_type]))
            
        if setid == None:
            # insert not exists
            setssql="INSERT INTO sets (idSet, strSet)  values(?, ?)"
            cursor.execute(setssql, (None,strSet))
            #if OK:
            result = cursor.fetchone()
            if result != None:
                setid = result[0]
        connection.commit()
        cursor.close()
        
        return True
    
    def updateBoxsetToKodiLibrary(self, boxsetmovie, boxset):
        strSet = boxset["Name"]
        kodiMovie = ReadKodiDB().getKodiMovie(boxsetmovie["Id"])
        if kodiMovie != None:
            WriteKodiDB().updateProperty(kodiMovie,"set",strSet,"movie",True)
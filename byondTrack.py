#!/usr/bin/python
import socket, struct, re, urllib2, os, string, datetime

# Load the data/ips.log into a list
def loadServerIPs(filename = 'Byond2IP/data/ips.log'):
	ips = list()
	with open(filename) as file:
		for line in file:
			line = line.strip()	
			if( line == "" ):	continue
			servername, serverip = line.split('#')
			if(serverip == ""):	continue	
			ips.append([servername,serverip])
	return ips

# Create the fake world.Export() data
def buildQuery(command):
	data = "?" + command
	return '\x00\x83' + struct.pack(">H", len(data)+6) + '\x00'*5 + data + '\x00' 
# Query a given server with the given command
def serverQuery(serverip, serverport, command, fallback = ""):
	# Attempt to open the socket, it is possible the server has went down since aquiring the IP
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(10)
		s.connect((serverip, int(serverport)))
		
		# Send the commands to the server
		s.send(buildQuery(command))
		result = s.recv(4096)
	except Exception:
		# Return an empty string if the connection fails to be established or timesout
		return ""	
	
	# If we got a junk response then fallback onto a safe command
	if len(result) < "16" and fallback != "":
		try:
			s.send(buildQuery(fallback))
			result = s.recv(4096)
		except Exception:
			return ""
	return result

# Get a copy of the Byond Hub text formatted
def getByondHub(url = 'http://www.byond.com/games/Exadv1/SpaceStation13'): 
	return urllib2.urlopen(url+'?format=text').read()	

# Gets the data associated with 'key' in dictionaryData
def findDictData(dictionaryData, key, getKey = False):
	for servername in dictionaryData:
		if key in servername:
			if getKey == True:
				return servername
			return dictionaryData[servername]
	return []

# Recursive wrapper that tests a string & matches a regex - fallbackData[test, regExp] | query[ip, port, command] 
def regexResult(result, test, regexExp, fallbackData = [], query = []):
	if test not in result:
		if len(query) == 3:
			# Ugly as heck Fallback into Server Query
			return regexResult(serverQuery(query[0], query[1], query[2]), fallbackData[0], fallbackData[1])
		
		# If there is fallback data then recursively call regexResult() with the fallback data
		if len(fallbackData) >= 1:
			return regexResult(result, fallbackData[0], fallbackData[1])

		return None
	
	return	re.search(regexExp, result).group(1)

# Converts an interger into hh:mm based on a interval
def int2Time(time, interval = 1):
	if time == None or time.isdigit() != True:
		return time

	# Convert ticks to seconds 
	time = int(time) / interval
	
	# Convert seconds to hh:mm
	m, s = divmod(int(time), 60)
	h, m = divmod(m, 60)
	return "%d:%02d" % (h, m) 

def writeData(dirname, filename, data):
	line = ""
	# Escape any funky special characters
	validChars = frozenset("-_.()[] %s%s" % (string.ascii_letters, string.digits))
	filename = ''.join(c for c in filename if c in validChars)
	
	# Check if the file exists, if not write a header into it
	if os.path.isfile('data/' + dirname + '/' + filename + '.log') == False:
		if dirname == "server":
			line = 	"timestamp\t\tplayers\tadmins\ttime\tmode\n"
		elif dirname == "player":
			line = "timestamp\t\tserver\n"

	# Add the timestamp to line
	line += datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\t"
	file = open('data/' + dirname + '/' + filename + '.log', 'a')
	# Covert the data from a list into a line
	for param in data:
		if param == "playerList":
			# Recursively call writeData() to write the players name
			for player in data[param]:
				writeData("player", player, {"server":filename})
			continue
		line += str(data[param]) + "\t"

	file.write(line + "\n")
	file.close()
	
def main():
	# Variable Definitions
	serverList, deadList, byondHubDict, serverStats = list(), list(), {}, {}

	# Get all of the IPs 
	serverList = loadServerIPs()
	
	# Add the private servers onto serverList
	privateServerList = loadServerIPs('data/privateIps.log')
	for server in privateServerList:
		serverList.append(server)
	
	for server in serverList: 
		# Seperate the IP out into ip and port
		serverip, serverport = server[1].split(':')
		# Try ?status=2 first to get the playerlist then fallback onto ?status if that didn't work
		result = serverQuery(serverip, serverport, "status=2", "status")
		
		#If we get no result then the server timed out or could not be connected to so add it to a list
		if(result == ""):
			# print("Error: Connection could not be established with " + server[0])
			deadList.append(server[0])
			continue
	
		if("player0" not in result and "&players=0" not in result):
			# Server cannot be queried so add it to the list of servers we'll use ByondHub extraction for
			byondHubDict[server[0]] = ["playerList"]
		
		# Initialise variables we'll store server stats into 
		players, admins, stationtime, mode = [None]*4 
		playerList = list()
		
		# Churn through the `?status` reply
		players = regexResult(result, "players=", 'players\=(\d{1,})')
		admins = regexResult(result, "admins=", 'admins\=(\d{1,})', ["admins=", 'admins\=(\d{1,})'], [serverip, serverport, "admins"])
		stationtime = regexResult(result, "stationtime=", 'stationtime=(.+?)\&', ["elapsed=",'elapsed=([\d|\w]+)'])		
		mode = regexResult(result, "mode=", 'mode\=(.+?)\&')
			
		# Stationtime - replace '%3a' with ':' or calculate hh:mm from number of ticks
		if stationtime != None:
			if '%3a' in stationtime:
				stationtime = stationtime.replace('%3a',':')
			
			stationtime = int2Time(stationtime, 0.5)		
		else: 
			# Final try some servers name it duration
			stationtime = regexResult(result, "duration=", 'duration=([\d|\w]+)')
			stationtime = int2Time(stationtime)
		# Clean up the playerList and to replace the `+` in names to an `_`	
		if "player0" in result:
			playerList = re.findall('player\d{1,}\=(.+?)\&', result)
			playerList = [playername.replace('+','_') for playername in playerList]
		
		# Servers format game modes differently (eg Extended, extended, EXTENDED) so just lower() them
		if mode != None:
			mode = mode.lower()

		# Check the stats have been set and if not add it to byondHubDict
		for var in [[players, "players"], [mode, "mode"]]:
			if var[0] != None:
				continue

			if server[0] in byondHubDict:
				byondHubDict[server[0]].append(var[1])
			else:
				byondHubDict[server[0]]  = [var[1]]

		# Server Print Status
		serverStats[server[0]] = {"players":players, "admins":admins, "stationtime":stationtime, "mode":mode, "playerList":playerList}
	
	# Download the server listing page 
	pageContent = getByondHub()
	
	worldRegList = re.findall(r"""world\/\d{1,}.+?status \= \"(\<.+?)players \= list\((.{0,}?)\)""", pageContent, re.S)
	
	# Convert the touple output of re.findall into a dictionary
	worldRegList = {v:k for v,k in worldRegList}		
	
	for server in byondHubDict:
		if "playerList" in byondHubDict[server]:
			serverStats[server]["playerList"] = findDictData(worldRegList, server)
			# Convert string to list if not None
			try:
				serverStats[server]["playerList"] = serverStats[server]["playerList"].replace("\"", "").split(',')
			except Exception:
				pass	
	
	# Finally lets write the data into a file
	for server in serverStats:
		# Write the server data into server/[servername].log
		writeData("server", server, serverStats[server])		
	
	#	print(server)
	#	print(serverStats[server])
	#	print('-'*80)

if __name__ == '__main__':
	main()

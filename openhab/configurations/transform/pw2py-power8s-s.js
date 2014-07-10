var json = JSON.parse(input);
//ws = json["switch"];
if (json.online) {
	ws = json.power8s.toFixed(1) + " W";
} else {
	ws = "offline";
}
ws;

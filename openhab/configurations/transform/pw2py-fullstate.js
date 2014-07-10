var json = JSON.parse(input);
var s = "";
s += "switch: " + json["switch"].toUpperCase();
s += ", sched{"+ json.schedname + "}:" + json.schedule.toUpperCase();
s += ", type: " + json.type;
s += ", name: " + json.location + "/" + json.name;
s += ", "  + (json.readonly ? "always ON" : "");
s += ", monitor: " + (json.monitor ? "yes" : "no");
s += ", log: " + (json.savelog ? "yes" : "no");
s += ", interval: " + json.interval + "m";
s += ", prod: " + (json.production ? "yes" : "no");
if (json.online) {
	// s = json.power8s.toFixed(1) + " W at ";
	// var date = new Date(1000 * json.powerts);
	// //s += date.toLocaleString();
	// s += date.toLocaleDateString() + " " + date.toLocaleTimeString();
	s += ", ONLINE";
} else {
	s += ", OFFLINE @ ";
	var date = new Date(1000 * json.lastseen);
	//s += date.toLocaleString();
	s += date.toLocaleDateString() + " " + date.toLocaleTimeString();
}
s;
var app = angular.module('pw2pyapp', ['ui.bootstrap']);

app.controller("pw2pyCtrl", function pw2pyCtrl($scope, $http, WS){
  $scope.conf = {static: []};
  $scope.config = {dynamic: []};
  $scope.circles = [];
  $scope.obj = {state: false};
  $scope.websockets = true;

  
  $scope.loadConfig = function () {
	console.log("loadConfig");
	$http.get("/pw-conf.json").
		success(function(data, status, headers, config) {
		    $scope.conf = data;
			$http.get("/pw-control.json").
				success(function(data, status, headers, config) {
					$scope.config = data;
					//Merge config
					for (var i=0; i<$scope.conf.static.length; i++) {
						var statconf = $scope.conf.static[i];
						var circle = {};
						for (var key in statconf) { circle[key] = statconf[key]; };
						var dynconf = getByMac($scope.config.dynamic, circle.mac);
						if (dynconf != null) {
							for (var key in dynconf) { circle[key] = dynconf[key]; };
						}
						circle['alwayson'] = (circle.always_on == "True") ? true : false
						if (circle['alwayson']) {
							circle.switch_state = 'on';
							circle.schedule_state = 'off';
						}
						circle['power'] = "-";
						circle['relayon'] = circle.switch_state
						
						circle.toolTip = "interval: " + circle.loginterval + " min.<br>"
						circle.toolTip += "monitor (10s): " + circle.monitor + "<br>"
						circle.toolTip += "save log (" + circle.loginterval + "m): " + circle.savelog + "<br>"
						circle.toolTip += "mac: " + circle.mac
						
						circle.icon = "fa-lightbulb-o"
						if (circle.category == "PV") {
							circle.icon = "fa-bolt"
						} else if (circle.category == "divers") {
							circle.icon = "fa-plug"
						}
						
						//TESTCODE
						//circle.alwayson = !(circle.name == 'circle+');
						
						
 						$scope.circles.push(circle);
						console.log(dynconf);
						console.log(statconf);
						console.log(circle);
						
						//WS.connect();
					}
				}).
				error(function(data, status, headers, config) {
				  // log error
				});
		}).
		error(function(data, status, headers, config) {
		  // log error
		});
  };
  
  function getByMac(arr, mac) {
	for (var i=0; i<arr.length; i++) {
	  if (arr[i].mac == mac) return arr[i];
	}
	return null;
}
  
  $scope.changeScheduleX = function(circle){
	console.log("schedule toggled to "+circle.schedule_state+" for "+circle.mac)
	};

  $scope.changeSwitchX = function(circle){
	console.log("switch   toggled to "+circle.switch_state+" for "+circle.mac);
	console.log(circle)
	};

  $scope.changeSwitch = function(circle){
	console.log("switch   toggled to "+circle.switch_state+" for "+circle.mac);
	//circle.schedule_state = 'off'
	
	//circle.relayon = circle.switch_state
	//MQTT topic, payload
	//plugwise2py/cmd/switch/000D6F0001Annnnn {"mac":"","cmd":"switch","val":"on"}
	var topic = "plugwise2py/cmd/switch/"+circle.mac
	var payload = {mac: circle.mac, cmd: "switch", val: circle.switch_state}
	var msg = {topic: topic, payload: payload}
	if ($scope.websockets) {
		$scope.send(JSON.stringify(msg))
	} else {
		$http.post("/mqtt/", msg).
			success(function(data, status, headers, config) {
				console.log("scheduled POST successful")
			}).
			error(function(data, status, headers, config) {
			  // log error
				console.log("scheduled POST error")
			});
	}
	return;
  };
  
  $scope.changeSchedule = function(circle){
	console.log("schedule   toggled to "+circle.schedule_state+" for "+circle.mac);
	//MQTT topic, payload
	//plugwise2py/cmd/schedule/000D6F0001Annnnn {"mac":"","cmd":"schedule","val":"on"}
	var topic = "plugwise2py/cmd/schedule/"+circle.mac
	var payload = {mac: circle.mac, cmd: "schedule", val: circle.schedule_state}
	var msg = {topic: topic, payload: payload}
	if ($scope.websockets) {
		$scope.send(JSON.stringify(msg))
	} else {
		$http.post("/mqtt/", msg).
			success(function(data, status, headers, config) {
				console.log("scheduled POST successful")
			}).
			error(function(data, status, headers, config) {
			  // log error
				console.log("scheduled POST error")
			});
	}
	return;
  };
  
  //Init
  $scope.loadConfig();
  
  //Handle WebSocket
  $scope.lastmessage = {};
 
  WS.subscribe(function(message) {
    //$scope.messages.push(message);
	$scope.lastmessage = message;
	var msg;
	try{
		msg = JSON.parse(message);
	}
	catch(e){
		console.log('Websocket message is not JSON: '+e.message);
		return;
	}
	var circle = getByMac($scope.circles, msg.mac);
	var power = "X"
	if (msg.hasOwnProperty('power')) {
		power = msg.power
	} else if (msg.hasOwnProperty('power8s')) {
		power = msg.power8s
	}
	if (power != "X") {
		if (circle.production == 'True') {
			power = -power;
		}
		circle.power = power.toFixed(1);
	}
	if (msg.hasOwnProperty('switch')) {
		circle.relayon = msg.switch
		circle.switch_state = msg.switch
	}
	//if (msg.hasOwnProperty('switchreq')) {
	//	circle.switch_state = msg.switchreq
	//}
	if (msg.hasOwnProperty('schedule')) {
		circle.schedule_state = msg.schedule
	}
	if (msg.hasOwnProperty('schedname')) {
		circle.schedule = msg.schedname
	}
    $scope.$apply();
  });
  WS.connect();
 
  $scope.connect = function() {
    WS.connect();
  }
 
  $scope.disconnect = function() {
    WS.disconnect();
	//console.log("WS.disconnect not yet implemented")
  }
 
  $scope.send = function(msg) {
    WS.send(msg);
  }

  $scope.sendtext = function() {
    WS.send($scope.text);
    $scope.text = "";
  }


});

app.directive('btnSwitch', function(){
    
  return {
    restrict : 'A',
    //require :  'ngModel',
    template : '<div class="btn-group" data-toggle="buttons-radio"><button type="button" class="btn btn-default" ng-class="{\'btn-warning\': state}" ng-click="turnSwitchOn(switch)">On</button><button type="button" class="btn btn-default" ng-class="{\'btn-default\': !state}" ng-click="turnSwitchOff(switch)">Off</button></div>',
    replace : true,
	scope: {
            switch: '='//,
            //state: '='
        },

    link : function(scope, element, attrs/*, ngModel*/){
        // // Listen for the button click event to enable binding
        // element.bind('click', function() {
          // scope.$apply(toggle);             
        // });
                   
        // // Toggle the model value
        // function toggle() {
           // var val = ngModel.$viewValue;
           // ngModel.$setViewValue(!val); 
           // render();          
        // } 
        scope.state = true;
		scope.turnSwitchOn = function (id) {
			console.log("switch on")
			console.log(id)
			scope.state = true;
		};
		scope.turnSwitchOff = function (id) {
			console.log("switch off")
			console.log(id)
			scope.state = false;
		};
    }
  };
});

app.factory('WS', function() {
  var service = {};
 
  service.connect = function() {
    if(service.ws) { return; }
 
    //var host = window.location.href.split("/")[2];
    var host = window.location.host;
	var ws;
	if (window.location.protocol == 'https:') {
		//ws = new WebSocket("wss://"+host+"/socket.ws");
		ws = new ReconnectingWebSocket("wss://"+host+"/socket.ws");
	} else {
		//ws = new WebSocket("ws://"+host+"/socket.ws");
		ws = new ReconnectingWebSocket("ws://"+host+"/socket.ws");
	}
 
    ws.onopen = function() {
      service.callback('{"result": "Succeeded to open a connection"}');
    };
 
    ws.onerror = function() {
      service.callback('{"result": "Failed to open a connection"}');
    }
 
    ws.onmessage = function(message) {
      service.callback(message.data);
    };
 
    service.ws = ws;
  }
 
  service.disconnect = function(message) {
    service.ws.close();
	service.ws = null
  }
 
  service.send = function(message) {
    service.ws.send(message);
  }
 
  service.subscribe = function(callback) {
    service.callback = callback;
  }
 
  return service;
});

// app.controller("WSCtrl", function WSCtrl($scope, WS) {
  // //$scope.messages = [];
  // $scope.lastmessage = {};
 
  // WS.subscribe(function(message) {
    // //$scope.messages.push(message);
	// $scope.lastmessage = JSON.parse(message);
    // $scope.$apply();
  // });
 
  // $scope.connect = function() {
    // WS.connect();
  // }
 
  // $scope.send = function() {
    // WS.send($scope.text);
    // $scope.text = "";
  // }
// })

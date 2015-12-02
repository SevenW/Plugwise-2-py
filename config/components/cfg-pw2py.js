var app = angular.module('schedules', ['ui.bootstrap']);

var WIDE = true;

app.controller("mainCtrl", function mainCtrl($scope, $http, $modal){
  $scope.tabs = [true, false, false, false];
  $scope.temp = false;
  
  $scope.conf = {static: []};
  $scope.config = {dynamic: []};
  $scope.circles = [];

  $scope.curSched = "";
  $scope.rows = [];
  $scope.changed = false;
  $scope.alrt = { type: 'success', msg: 'ok' };
  $scope.mctrl = {addMAC: "", addName: "", description: "description"}
  $scope.mctrl.schedule = (WIDE ? zeroData() : transpose(zeroData()));
  $scope.state = {changed: false, fit: true};
  
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
						circle.alwayson = !(circle.name == 'circle+');
						
						
 						$scope.circles.push(circle);
						
						//Enrich dynamic config (temporary code)
						if (!dynconf.hasOwnProperty('location')) {
							dynconf['location'] = statconf.location;
						}
						if (!dynconf.hasOwnProperty('category')) {
							dynconf['category'] = statconf.category;
						}
						
						
						console.log(dynconf);
						console.log(statconf);
						console.log(circle);
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
  
  function getIdxByMac(arr, mac) {
	for (var i=0; i<arr.length; i++) {
	  if (arr[i].mac == mac) return i;
	}
	return null;
  }
  
  function getByMac(arr, mac) {
	for (var i=0; i<arr.length; i++) {
	  if (arr[i].mac == mac) return arr[i];
	}
	return null;
  }
  
  //Init
  $scope.loadConfig();
  
  $http.get('/schedules').
    success(function(data, status, headers, config) {
      $scope.rows = data.sort();
    }).
    error(function(data, status, headers, config) {
      // log error
    });
	 
  $scope.addRow = function(){
    name = $scope.mctrl.addName;
	$http.post("/schedules/" + name + ".json", createSchedule(name)).
		success(function(data, status, headers, config) {
			console.log("scheduled POST successful")
		}).
		error(function(data, status, headers, config) {
		  // log error
			console.log("scheduled POST error")
		});
	$scope.temp = false;
    $scope.mctrl.addName="";
	$scope.rows.sort();
  };
  
  $scope.deleteRow = function(row){
    $scope.rows.splice($scope.rows.indexOf(row),1);
  };
  
  $scope.plural = function (tab){
    return tab.length > 1 ? 's': ''; 
  };
  
  $scope.addTemp = function(){
    if($scope.temp) $scope.rows.pop(); 
    else if($scope.mctrl.addName) $scope.temp = true;
    
    if($scope.mctrl.addName) $scope.rows.push($scope.mctrl.addName);
    else $scope.temp = false;
  };
  
  $scope.isTemp = function(i){
    return i==$scope.rows.length-1 && $scope.temp;
  };
  
  $scope.editRow = function (row) {
    $scope.tabs[1] = false;
    $scope.tabs[2] = true;
    $scope.curSched = row;
	console.log("editRow "+row);
	$http.get("/schedules/" + row + ".json").
		success(function(data, status, headers, config) {
		  $scope.raw = data;
		  $scope.mctrl.description = $scope.raw.description;
		  $scope.mctrl.schedule = angular.copy(WIDE ? $scope.raw.schedule : transpose($scope.raw.schedule));
		  $scope.curInfo = $scope.raw.name;
		  $scope.alrt = { type: 'success', msg: 'schedule loaded' };
		  $scope.state.changed = false;
		}).
		error(function(data, status, headers, config) {
		  // log error
		});
  };
  
  $scope.saveSchedule = function(){
	$scope.raw.schedule = (WIDE ? $scope.mctrl.schedule : transpose($scope.mctrl.schedule))
	$scope.raw.description = $scope.mctrl.description;
	$http.post("/schedules/" + $scope.curSched + ".json", $scope.raw).
		success(function(data, status, headers, config) {
			console.log("scheduled POST successful")
		}).
		error(function(data, status, headers, config) {
		  // log error
			console.log("scheduled POST error")
		});

	$scope.state.changed = false;
	$scope.alrt.msg = 'schedule saved';
	return;
  };
  
  $scope.cancelSchedule = function(){
	$scope.mctrl.schedule = angular.copy(WIDE ? $scope.raw.schedule : transpose($scope.raw.schedule));
	$scope.mctrl.description = $scope.raw.description;
	$scope.state.changed = false;
	$scope.alrt.msg = 'reverted to saved';
	return;
  };
  
  $scope.setChanged = function(){
	$scope.changed = true;
	return;
  }; 
  
  $scope.toggleWidth = function(){
    console.log("toggleWidth()");
	$scope.state.fit = !$scope.state.fit;
	return;
  }; 
  
  
	function transpose(array) {
	  var newArray = array[0].map(function(col, i) { 
		return array.map(function(row) { 
		  return row[i] 
		});
	  });
	  return newArray
	};

	function zeroData () {
		var matrix = [];
		for (var j = 0; j < 7; j++) {
			matrix.push(Array.apply(null, new Array(96)).map(Number.prototype.valueOf,0));
		}
		return matrix;
	}
	
	function createSchedule (newname) {
		var raw = {name: newname, description: "always on"};
		raw.schedule = zeroData();
		return raw;
	}
	
  $scope.editCircle = function (circle) {
	var conf = {static: {}, dynamic: {}};
	conf.static = getByMac($scope.conf.static, circle.mac)
	conf.dynamic = getByMac($scope.config.dynamic, circle.mac)
    var modalInstance = $modal.open({
      templateUrl: 'components/editform.html',
      controller: modalInstanceCtrl,
	  conf: conf,
	  resolve: {
		  conf: function() {
			return angular.copy(conf);
	      }
	  }
	});

    modalInstance.result.then(function (conf) {
      //$scope.selected = selectedItem;
	  $scope.updated_conf = conf;
	  //sync some fields between static and dynamic conf
	  $scope.updated_conf.dynamic.mac = $scope.updated_conf.static.mac
	  $scope.updated_conf.static.name = $scope.updated_conf.dynamic.name
	  $scope.updated_conf.static.location = $scope.updated_conf.dynamic.location
	  $scope.updated_conf.static.category = $scope.updated_conf.dynamic.category
	  
	  var i_stat = getIdxByMac($scope.conf.static, $scope.updated_conf.static.mac)
	  var i_dyna = getIdxByMac($scope.config.dynamic, $scope.updated_conf.static.mac)
	  
	  $scope.conf.static[i_stat] = $scope.updated_conf.static
	  $scope.config.dynamic[i_dyna] = $scope.updated_conf.dynamic
	  
	  //ONLY save dynamic (for the moment)
	  $http.post("/pw-control.json", $scope.config).
		success(function(data, status, headers, config) {
			console.log("pw-control.json POST successful")
		}).
		error(function(data, status, headers, config) {
		  // log error
			console.log("pw-control.json POST error")
		});

	  var i_circ = getIdxByMac($scope.circles, $scope.updated_conf.static.mac)
	  for (var key in $scope.updated_conf.dynamic) { $scope.circles[i_circ][key] = $scope.updated_conf.dynamic[key]; };
	  console.log('save edit of ' + conf.dynamic.name);
	  

    }, function () {
      console.log('cancelled edit of ' + conf.dynamic.name);
    });
  };

	
})

app.directive('handsontable', function($window){
    return {
        restrict: 'EAC',
        scope: {
            schedule: '=',
            alrt: '=',
			unsaved: '=',
			fit: '=',
            valchanged: '&'
        },
        replace: true,
        template: '<div></br></br></br></div>',
        link: function(scope, elem, attrs ){
			Handsontable.renderers.registerRenderer('valueRenderer', valueRenderer); //maps function to lookup string
			//$(elem).handsontable({
			elem.handsontable({
			  startRows: (WIDE ? 7 : 96),
			  startCols: (WIDE ? 96 : 7),
			  maxRows: (WIDE ? 7 : 96),
			  maxCols: (WIDE ? 96 : 7),
			  colWidths: 36,
			  //rowHeights: 36,
			  rowHeaders: dayheaders,
			  colHeaders: columnheaders_wide,
			  cells: function (row, col, prop) {
				var cellProperties = {};
				cellProperties.type = 'numeric';
				cellProperties.renderer = "valueRenderer"; //uses lookup map
				cellProperties.data = 0;
				return cellProperties;
				},
              data: scope.schedule,
			  beforeChange: function (changes, source) {
				for (var i = changes.length - 1; i >= 0; i--) {
				  if (changes[i][3] == null || changes[i][3] === '') {
					changes[i][3] = 0;
				  } else if (isNaN(+changes[i][3])) {
					return false;
				  } else if  (changes[i][3] < 0) {
					changes[i][3] = -1;
				  } else if (changes[i][3] > 3000) {
					changes[i][3] = -1; //ON in case of very high standby value
				  }
				}
				if (source != 'loadData') {
					scope.alrt.type = 'success';
					scope.alrt.msg = 'schedule modified';
					scope.unsaved = true;
					scope.valchanged();
					scope.$apply();
				}
			  },
			  afterLoadData: function () {
				var hot = elem.handsontable('getInstance');
				scope.hot = hot;
				for (var r = 0; r < scope.hot.countRows(); r++) {
					for (var c = 0; c < scope.hot.countCols(); c++) {
						var value = scope.hot.getDataAtCell(r, c);
						if (value == null || value === '') {
							scope.hot.setDataAtCell(r, c, 0);
						} else if (typeof value === 'string') {
							scope.hot.setDataAtCell(r, c, parseInt(value));
						}
					}
				}
			  },
                
            })
			scope.hot = elem.handsontable('getInstance');
			scope.$watch("schedule", function() {
				console.log("HOT loadData");
				scope.hot.loadData(scope.schedule);
			});
			scope.$watch("fit", function() {
				console.log("Toggle fit");
				if (scope.fit) {
					//scope.hot.colWidths = 15;
					//elem.width = $window.innerWidth;
					var w = ($window.innerWidth - 50 ) / 96;
					w=Math.max(1, Math.floor(w));
					scope.hot.updateSettings({colWidths: w});
				} else {
					//scope.hot.colWidths = 30;
					scope.hot.updateSettings({colWidths: 36});
				}
				//scope.hot.loadData(scope.schedule);
				//scope.hot.render();
			});
			
			//local functions for handsontable directive
            function columnheaders_wide(index) {
				var hour = Math.floor(index /4);
				var minute = 15 * (index % 4);
				var hour_s = (hour < 10 ? "0" + hour : hour);
				var minute_s = (minute < 10 ? "0" + minute : minute);
				var time = (hour < 10 ? "0" + hour : hour) + "00";
				j = index % 4;
				if (j==0) {
					//return "<b>"+(hour < 10 ? "" : time[0])+"</br>"+time[1]+"</br>"+time[2]+"</br>"+time[3]+"</b>";
					//return '<div class="htRight" style="color:blue;letter-spacing: -1px;"><small>'+hour_s+'</small></div>';
					return '<div class="htRight text-info" style="letter-spacing: -1px;"><small>'+hour_s+'</small></div>';
					};
				//return '<div class="htRight" style="color:lightblue;"><small><small>'+minute_s+'</small></small></div>';
				return '<div class="htRight text-primary"><small><small>'+minute_s+'</small></small></div>';
			};
			function rowheaders_wide(index) {
				var hour = Math.floor(index /4);
				var minute = 15 * (index % 4);
				var time = (hour < 10 ? "0" + hour : hour) + ":" + (minute < 10 ? "0" + minute : minute);
				return time;
			};
			function dayheaders(index) {
				var days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
				return '<div class="htLeft" style="color:blue;"><small>'+days[index]+'</small></div>';
			};
			function valueRenderer(instance, td, row, col, prop, value, cellProperties) {
			  Handsontable.renderers.TextRenderer.apply(this, arguments);
			  if (value == null || value === '') {
				td.style.background = 'red';
			  } else if (parseInt(value, 10) == 0) {
				//td.className = 'schedule-off';
				td.style.background = '#bbb';
				td.style.color = '#bbb'
			  } else if (parseInt(value, 10) < 0) { 
				//td.className = 'schedule-on';
				td.style.background = '#f0ad4e'
				td.style.color = '#f0ad4e'
			  } else {
				//td.className = 'schedule-on';
				td.style.background = '#f8d6a6'
				td.style.fontStyle = 'italic';
				td.style.fontSize = 'smaller';
				//td.style.textAlign = 'right';
				//td.className = 'htRight';
			  }
			};
        }
    }
})

app.controller('ConfirmDeleteCtrl', function ConfirmDeleteCtrl($scope, $http, modalService) {
    $scope.deleteSchedule = function (schedName) {
        var modalOptions = {
            closeButtonText: 'Cancel',
            actionButtonText: 'Delete Schedule',
            headerText: 'Delete ' + schedName + '?',
            bodyText: 'Are you sure you want to delete this schedule?'
        };

        modalService.showModal({}, modalOptions).then(function (result) {
            console.log("Delete confirmed!");
			$http.post("/schedules", {'delete': schedName+'.json'}).
				success(function(data, status, headers, config) {
					console.log("scheduled POST successful")
					$scope.deleteRow(schedName);
				}).
				error(function(data, status, headers, config) {
				  // log error
					console.log("scheduled POST error")
				});
        });
    }
});


var modalInstanceCtrl = function ($scope, $modalInstance, conf) {

  $scope.conf = conf;
  //$scope.selected = {
  //  item: $scope.items[0]
  //};

  $scope.ok = function () {
    $modalInstance.close($scope.conf);
  };

  $scope.cancel = function () {
    $modalInstance.dismiss('cancel');
  };
};

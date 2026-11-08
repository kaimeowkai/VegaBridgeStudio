import {configureDesign} from './src/ui';
configureDesign('decision-dock');
import React from 'react';
import {AppRegistry} from 'react-native';
import {DecisionDock} from './src/apps';
const Starter = DecisionDock;
AppRegistry.registerComponent('com.vegabridge.samples.decisiondock.main', () => Starter);

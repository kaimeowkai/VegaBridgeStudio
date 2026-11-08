import {configureDesign} from './src/ui';
configureDesign('session-canvas');
import React from 'react';
import {AppRegistry} from 'react-native';
import {SessionCanvas} from './src/apps';
const Starter = SessionCanvas;
AppRegistry.registerComponent('com.vegabridge.samples.sessioncanvas.main', () => Starter);

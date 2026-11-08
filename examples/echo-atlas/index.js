import {configureDesign} from './src/ui';
configureDesign('echo-atlas');
import React from 'react';
import {AppRegistry} from 'react-native';
import {EchoAtlas} from './src/games';
const Starter = EchoAtlas;
AppRegistry.registerComponent('com.vegabridge.samples.echoatlas.main', () => Starter);

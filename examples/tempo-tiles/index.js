import {configureDesign} from './src/ui';
configureDesign('tempo-tiles');
import React from 'react';
import {AppRegistry} from 'react-native';
import {TempoTiles} from './src/apps';
const Starter = TempoTiles;
AppRegistry.registerComponent('com.vegabridge.samples.tempotiles.main', () => Starter);

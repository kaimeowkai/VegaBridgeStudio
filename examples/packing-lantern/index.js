import {configureDesign} from './src/ui';
configureDesign('packing-lantern');
import React from 'react';
import {AppRegistry} from 'react-native';
import {PackingLantern} from './src/apps';
const Starter = PackingLantern;
AppRegistry.registerComponent('com.vegabridge.samples.packinglantern.main', () => Starter);

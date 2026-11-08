import {configureDesign} from './src/ui';
configureDesign('orbit-orchard');
import React from 'react';
import {AppRegistry} from 'react-native';
import {OrbitOrchard} from './src/games';
const Starter = OrbitOrchard;
AppRegistry.registerComponent('com.vegabridge.samples.orbitorchard.main', () => Starter);

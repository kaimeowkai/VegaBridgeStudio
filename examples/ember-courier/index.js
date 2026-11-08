import {configureDesign} from './src/ui';
configureDesign('ember-courier');
import React from 'react';
import {AppRegistry} from 'react-native';
import {EmberCourier} from './src/games';
const Starter = EmberCourier;
AppRegistry.registerComponent('com.vegabridge.samples.embercourier.main', () => Starter);

import {configureDesign} from './src/ui';
configureDesign('pantry-orbit');
import React from 'react';
import {AppRegistry} from 'react-native';
import {PantryOrbit} from './src/apps';
const Starter = PantryOrbit;
AppRegistry.registerComponent('com.vegabridge.samples.pantryorbit.main', () => Starter);

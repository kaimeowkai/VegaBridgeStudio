import {configureDesign} from './src/ui';
configureDesign('beacon-weave');
import React from 'react';
import {AppRegistry} from 'react-native';
import {BeaconWeave} from './src/games';
const Starter = BeaconWeave;
AppRegistry.registerComponent('com.vegabridge.samples.beaconweave.main', () => Starter);

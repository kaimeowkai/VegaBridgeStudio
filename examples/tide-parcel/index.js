import {configureDesign} from './src/ui';
configureDesign('tide-parcel');
import React from 'react';
import {AppRegistry} from 'react-native';
import {TideParcel} from './src/games';
const Starter = TideParcel;
AppRegistry.registerComponent('com.vegabridge.samples.tideparcel.main', () => Starter);

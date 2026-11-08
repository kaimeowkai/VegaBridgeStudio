import {configureDesign} from './src/ui';
configureDesign('measure-mosaic');
import React from 'react';
import {AppRegistry} from 'react-native';
import {MeasureMosaic} from './src/apps';
const Starter = MeasureMosaic;
AppRegistry.registerComponent('com.vegabridge.samples.measuremosaic.main', () => Starter);

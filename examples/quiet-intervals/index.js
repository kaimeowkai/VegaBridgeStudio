import {configureDesign} from './src/ui';
configureDesign('quiet-intervals');
import React from 'react';
import {AppRegistry} from 'react-native';
import {QuietIntervals} from './src/apps';
const Starter = QuietIntervals;
AppRegistry.registerComponent('com.vegabridge.samples.quietintervals.main', () => Starter);

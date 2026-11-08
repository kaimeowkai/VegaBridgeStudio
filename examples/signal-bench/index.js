import {configureDesign} from './src/ui';
configureDesign('signal-bench');
import React from 'react';
import {AppRegistry} from 'react-native';
import {SignalBench} from './src/apps';
const Starter = SignalBench;
AppRegistry.registerComponent('com.vegabridge.samples.signalbench.main', () => Starter);

import {configureDesign} from './src/ui';
configureDesign('split-ledger');
import React from 'react';
import {AppRegistry} from 'react-native';
import {SplitLedger} from './src/apps';
const Starter = SplitLedger;
AppRegistry.registerComponent('com.vegabridge.samples.splitledger.main', () => Starter);

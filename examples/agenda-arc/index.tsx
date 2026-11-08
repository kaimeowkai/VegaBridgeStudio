import {configureDesign} from './src/ui';
configureDesign('agenda-arc');
import React from 'react';
import {AppRegistry} from 'react-native';
import {AgendaArc} from './src/apps';
const Starter: React.ComponentType = AgendaArc;
AppRegistry.registerComponent('com.vegabridge.samples.agendaarc.main', () => Starter);

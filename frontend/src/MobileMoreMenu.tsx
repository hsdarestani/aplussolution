import React, { useState } from 'react';
import { IonIcon } from '@ionic/react';
import {
  businessOutline,
  calendarOutline,
  documentTextOutline,
  exitOutline,
  locationOutline,
  megaphoneOutline,
  moonOutline,
  peopleOutline,
  personCircleOutline,
  settingsOutline,
  stopwatchOutline,
  sunnyOutline,
} from 'ionicons/icons';
import { applyMobileAppearance, getMobileAppearance, MobileAppearance } from './mobileAppearance';

const menuIcons: Record<string, string> = {
  messages: megaphoneOutline,
  operations: calendarOutline,
  documents: documentTextOutline,
  contracts: documentTextOutline,
  ranking: peopleOutline,
  ratings: peopleOutline,
  orders: businessOutline,
  people: peopleOutline,
  settings: settingsOutline,
};

function Row({icon,label,onClick,active=false}:{icon:string;label:string;onClick:()=>void;active?:boolean}) {
  return <button type="button" className={`wiw-more-row ${active?'active':''}`} onClick={onClick}>
    <IonIcon icon={icon}/><span>{label}</span>
  </button>;
}

export default function MobileMoreMenu({user,items,view,navigate,onLogout}:{user:any;items:[string,string][];view:string;navigate:(view:any)=>void;onLogout:()=>void}) {
  const [appearance,setAppearance] = useState<MobileAppearance>(()=>getMobileAppearance());
  const setTheme=(next:MobileAppearance)=>{setAppearance(next);applyMobileAppearance(next);};
  const companyItems = items.filter(([key])=>!['profile','time'].includes(key));
  return <div className="wiw-more-screen" data-testid="wiw-more-screen">
    <div className="wiw-more-title">Mehr</div>
    <div className="wiw-more-user">{user.name}</div>
    <Row icon={personCircleOutline} label="Profil & Einstellungen" onClick={()=>navigate('profile')} active={view==='profile'}/>
    {user.role==='worker'&&<Row icon={calendarOutline} label="Verfügbarkeit" onClick={()=>navigate('operations')} active={view==='operations'}/>} 
    <Row icon={stopwatchOutline} label="Meine Stunden" onClick={()=>navigate('time')} active={view==='time'}/>
    <div className="wiw-more-theme">
      <span>Darstellung</span>
      <div role="group" aria-label="Darstellung wählen">
        <button type="button" className={appearance==='light'?'active':''} onClick={()=>setTheme('light')}><IonIcon icon={sunnyOutline}/>Hell</button>
        <button type="button" className={appearance==='dark'?'active':''} onClick={()=>setTheme('dark')}><IonIcon icon={moonOutline}/>Dunkel</button>
      </div>
    </div>
    <Row icon={exitOutline} label="Abmelden" onClick={onLogout}/>
    <div className="wiw-more-section">A+ Solution GmbH</div>
    {companyItems.map(([key,label])=><Row key={key} icon={menuIcons[key]||locationOutline} label={label} onClick={()=>navigate(key)} active={view===key}/>)}
  </div>;
}

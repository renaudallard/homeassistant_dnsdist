function t(t,e,i,s){var r,o=arguments.length,n=o<3?e:null===s?s=Object.getOwnPropertyDescriptor(e,i):s;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)n=Reflect.decorate(t,e,i,s);else for(var a=t.length-1;a>=0;a--)(r=t[a])&&(n=(o<3?r(n):o>3?r(e,i,n):r(e,i))||n);return o>3&&n&&Object.defineProperty(e,i,n),n}"function"==typeof SuppressedError&&SuppressedError;const e=globalThis,i=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s=Symbol(),r=new WeakMap;let o=class{constructor(t,e,i){if(this._$cssResult$=!0,i!==s)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const i=void 0!==e&&1===e.length;i&&(t=r.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),i&&r.set(e,t))}return t}toString(){return this.cssText}};const n=(t,...e)=>{const i=1===t.length?t[0]:e.reduce((e,i,s)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[s+1],t[0]);return new o(i,t,s)},a=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const i of t.cssRules)e+=i.cssText;return(t=>new o("string"==typeof t?t:t+"",void 0,s))(e)})(t):t,{is:c,defineProperty:l,getOwnPropertyDescriptor:d,getOwnPropertyNames:h,getOwnPropertySymbols:p,getPrototypeOf:u}=Object,f=globalThis,g=f.trustedTypes,m=g?g.emptyScript:"",_=f.reactiveElementPolyfillSupport,v=(t,e)=>t,y={toAttribute(t,e){switch(e){case Boolean:t=t?m:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let i=t;switch(e){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t)}catch(t){i=null}}return i}},b=(t,e)=>!c(t,e),$={attribute:!0,type:String,converter:y,reflect:!1,useDefault:!1,hasChanged:b};Symbol.metadata??=Symbol("metadata"),f.litPropertyMetadata??=new WeakMap;let x=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=$){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const i=Symbol(),s=this.getPropertyDescriptor(t,i,e);void 0!==s&&l(this.prototype,t,s)}}static getPropertyDescriptor(t,e,i){const{get:s,set:r}=d(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:s,set(e){const o=s?.call(this);r?.call(this,e),this.requestUpdate(t,o,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??$}static _$Ei(){if(this.hasOwnProperty(v("elementProperties")))return;const t=u(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(v("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(v("properties"))){const t=this.properties,e=[...h(t),...p(t)];for(const i of e)this.createProperty(i,t[i])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const i=this._$Eu(t,e);void 0!==i&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const i=new Set(t.flat(1/0).reverse());for(const t of i)e.unshift(a(t))}else void 0!==t&&e.push(a(t));return e}static _$Eu(t,e){const i=e.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const i of e.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,s)=>{if(i)t.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of s){const s=document.createElement("style"),r=e.litNonce;void 0!==r&&s.setAttribute("nonce",r),s.textContent=i.cssText,t.appendChild(s)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,i){this._$AK(t,i)}_$ET(t,e){const i=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,i);if(void 0!==s&&!0===i.reflect){const r=(void 0!==i.converter?.toAttribute?i.converter:y).toAttribute(e,i.type);this._$Em=t,null==r?this.removeAttribute(s):this.setAttribute(s,r),this._$Em=null}}_$AK(t,e){const i=this.constructor,s=i._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const t=i.getPropertyOptions(s),r="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:y;this._$Em=s;const o=r.fromAttribute(e,t.type);this[s]=o??this._$Ej?.get(s)??o,this._$Em=null}}requestUpdate(t,e,i,s=!1,r){if(void 0!==t){const o=this.constructor;if(!1===s&&(r=this[t]),i??=o.getPropertyOptions(t),!((i.hasChanged??b)(r,e)||i.useDefault&&i.reflect&&r===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,i))))return;this.C(t,e,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:i,reflect:s,wrapped:r},o){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),!0!==r||void 0!==o)||(this._$AL.has(t)||(this.hasUpdated||i||(e=void 0),this._$AL.set(t,e)),!0===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,i]of t){const{wrapped:t}=i,s=this[e];!0!==t||this._$AL.has(e)||void 0===s||this.C(e,void 0,i,s)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};x.elementStyles=[],x.shadowRootOptions={mode:"open"},x[v("elementProperties")]=new Map,x[v("finalized")]=new Map,_?.({ReactiveElement:x}),(f.reactiveElementVersions??=[]).push("2.1.2");const w=globalThis,A=t=>t,k=w.trustedTypes,C=k?k.createPolicy("lit-html",{createHTML:t=>t}):void 0,E="$lit$",S=`lit$${Math.random().toFixed(9).slice(2)}$`,M="?"+S,R=`<${M}>`,P=document,N=()=>P.createComment(""),T=t=>null===t||"object"!=typeof t&&"function"!=typeof t,U=Array.isArray,D="[ \t\n\f\r]",O=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,z=/-->/g,L=/>/g,H=RegExp(`>|${D}(?:([^\\s"'>=/]+)(${D}*=${D}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),j=/'/g,I=/"/g,q=/^(?:script|style|textarea|title)$/i,F=(t=>(e,...i)=>({_$litType$:t,strings:e,values:i}))(1),B=Symbol.for("lit-noChange"),V=Symbol.for("lit-nothing"),W=new WeakMap,G=P.createTreeWalker(P,129);function Y(t,e){if(!U(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==C?C.createHTML(e):e}const K=(t,e)=>{const i=t.length-1,s=[];let r,o=2===e?"<svg>":3===e?"<math>":"",n=O;for(let e=0;e<i;e++){const i=t[e];let a,c,l=-1,d=0;for(;d<i.length&&(n.lastIndex=d,c=n.exec(i),null!==c);)d=n.lastIndex,n===O?"!--"===c[1]?n=z:void 0!==c[1]?n=L:void 0!==c[2]?(q.test(c[2])&&(r=RegExp("</"+c[2],"g")),n=H):void 0!==c[3]&&(n=H):n===H?">"===c[0]?(n=r??O,l=-1):void 0===c[1]?l=-2:(l=n.lastIndex-c[2].length,a=c[1],n=void 0===c[3]?H:'"'===c[3]?I:j):n===I||n===j?n=H:n===z||n===L?n=O:(n=H,r=void 0);const h=n===H&&t[e+1].startsWith("/>")?" ":"";o+=n===O?i+R:l>=0?(s.push(a),i.slice(0,l)+E+i.slice(l)+S+h):i+S+(-2===l?e:h)}return[Y(t,o+(t[i]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),s]};class J{constructor({strings:t,_$litType$:e},i){let s;this.parts=[];let r=0,o=0;const n=t.length-1,a=this.parts,[c,l]=K(t,e);if(this.el=J.createElement(c,i),G.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(s=G.nextNode())&&a.length<n;){if(1===s.nodeType){if(s.hasAttributes())for(const t of s.getAttributeNames())if(t.endsWith(E)){const e=l[o++],i=s.getAttribute(t).split(S),n=/([.?@])?(.*)/.exec(e);a.push({type:1,index:r,name:n[2],strings:i,ctor:"."===n[1]?et:"?"===n[1]?it:"@"===n[1]?st:tt}),s.removeAttribute(t)}else t.startsWith(S)&&(a.push({type:6,index:r}),s.removeAttribute(t));if(q.test(s.tagName)){const t=s.textContent.split(S),e=t.length-1;if(e>0){s.textContent=k?k.emptyScript:"";for(let i=0;i<e;i++)s.append(t[i],N()),G.nextNode(),a.push({type:2,index:++r});s.append(t[e],N())}}}else if(8===s.nodeType)if(s.data===M)a.push({type:2,index:r});else{let t=-1;for(;-1!==(t=s.data.indexOf(S,t+1));)a.push({type:7,index:r}),t+=S.length-1}r++}}static createElement(t,e){const i=P.createElement("template");return i.innerHTML=t,i}}function Z(t,e,i=t,s){if(e===B)return e;let r=void 0!==s?i._$Co?.[s]:i._$Cl;const o=T(e)?void 0:e._$litDirective$;return r?.constructor!==o&&(r?._$AO?.(!1),void 0===o?r=void 0:(r=new o(t),r._$AT(t,i,s)),void 0!==s?(i._$Co??=[])[s]=r:i._$Cl=r),void 0!==r&&(e=Z(t,r._$AS(t,e.values),r,s)),e}class Q{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:i}=this._$AD,s=(t?.creationScope??P).importNode(e,!0);G.currentNode=s;let r=G.nextNode(),o=0,n=0,a=i[0];for(;void 0!==a;){if(o===a.index){let e;2===a.type?e=new X(r,r.nextSibling,this,t):1===a.type?e=new a.ctor(r,a.name,a.strings,this,t):6===a.type&&(e=new rt(r,this,t)),this._$AV.push(e),a=i[++n]}o!==a?.index&&(r=G.nextNode(),o++)}return G.currentNode=P,s}p(t){let e=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(t,i,e),e+=i.strings.length-2):i._$AI(t[e])),e++}}class X{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,i,s){this.type=2,this._$AH=V,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=Z(this,t,e),T(t)?t===V||null==t||""===t?(this._$AH!==V&&this._$AR(),this._$AH=V):t!==this._$AH&&t!==B&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>U(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==V&&T(this._$AH)?this._$AA.nextSibling.data=t:this.T(P.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:i}=t,s="number"==typeof i?this._$AC(t):(void 0===i.el&&(i.el=J.createElement(Y(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(e);else{const t=new Q(s,this),i=t.u(this.options);t.p(e),this.T(i),this._$AH=t}}_$AC(t){let e=W.get(t.strings);return void 0===e&&W.set(t.strings,e=new J(t)),e}k(t){U(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let i,s=0;for(const r of t)s===e.length?e.push(i=new X(this.O(N()),this.O(N()),this,this.options)):i=e[s],i._$AI(r),s++;s<e.length&&(this._$AR(i&&i._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=A(t).nextSibling;A(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class tt{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,i,s,r){this.type=1,this._$AH=V,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=r,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=V}_$AI(t,e=this,i,s){const r=this.strings;let o=!1;if(void 0===r)t=Z(this,t,e,0),o=!T(t)||t!==this._$AH&&t!==B,o&&(this._$AH=t);else{const s=t;let n,a;for(t=r[0],n=0;n<r.length-1;n++)a=Z(this,s[i+n],e,n),a===B&&(a=this._$AH[n]),o||=!T(a)||a!==this._$AH[n],a===V?t=V:t!==V&&(t+=(a??"")+r[n+1]),this._$AH[n]=a}o&&!s&&this.j(t)}j(t){t===V?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class et extends tt{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===V?void 0:t}}class it extends tt{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==V)}}class st extends tt{constructor(t,e,i,s,r){super(t,e,i,s,r),this.type=5}_$AI(t,e=this){if((t=Z(this,t,e,0)??V)===B)return;const i=this._$AH,s=t===V&&i!==V||t.capture!==i.capture||t.once!==i.once||t.passive!==i.passive,r=t!==V&&(i===V||s);s&&this.element.removeEventListener(this.name,this,i),r&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class rt{constructor(t,e,i){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(t){Z(this,t)}}const ot=w.litHtmlPolyfillSupport;ot?.(J,X),(w.litHtmlVersions??=[]).push("3.3.2");const nt=globalThis;class at extends x{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,i)=>{const s=i?.renderBefore??e;let r=s._$litPart$;if(void 0===r){const t=i?.renderBefore??null;s._$litPart$=r=new X(e.insertBefore(N(),t),t,void 0,i??{})}return r._$AI(t),r})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return B}}at._$litElement$=!0,at.finalized=!0,nt.litElementHydrateSupport?.({LitElement:at});const ct=nt.litElementPolyfillSupport;ct?.({LitElement:at}),(nt.litElementVersions??=[]).push("4.2.2");const lt=t=>(e,i)=>{void 0!==i?i.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)},dt={attribute:!0,type:String,converter:y,reflect:!1,hasChanged:b},ht=(t=dt,e,i)=>{const{kind:s,metadata:r}=i;let o=globalThis.litPropertyMetadata.get(r);if(void 0===o&&globalThis.litPropertyMetadata.set(r,o=new Map),"setter"===s&&((t=Object.create(t)).wrapped=!0),o.set(i.name,t),"accessor"===s){const{name:s}=i;return{set(i){const r=e.get.call(this);e.set.call(this,i),this.requestUpdate(s,r,t,!0,i)},init(e){return void 0!==e&&this.C(s,void 0,t,e),e}}}if("setter"===s){const{name:s}=i;return function(i){const r=this[s];e.call(this,i),this.requestUpdate(s,r,t,!0,i)}}throw Error("Unsupported decorator location: "+s)};function pt(t){return(e,i)=>"object"==typeof i?ht(t,e,i):((t,e,i)=>{const s=e.hasOwnProperty(i);return e.constructor.createProperty(i,t),s?Object.getOwnPropertyDescriptor(e,i):void 0})(t,e,i)}function ut(t){return pt({...t,state:!0,attribute:!1})}const ft=n`
  :host {
    --dnsdist-card-background: var(--ha-card-background, var(--card-background-color, #fff));
    --dnsdist-primary-text: var(--primary-text-color, #212121);
    --dnsdist-secondary-text: var(--secondary-text-color, #727272);
    --dnsdist-accent: var(--primary-color, #03a9f4);
    --dnsdist-success: var(--success-color, #4caf50);
    --dnsdist-warning: var(--warning-color, #ff9800);
    --dnsdist-error: var(--error-color, #f44336);
    --dnsdist-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --dnsdist-border-radius: var(--ha-card-border-radius, 12px);
  }

  ha-card {
    padding: 16px;
    overflow: hidden;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--dnsdist-divider);
  }

  .card-title {
    font-size: 1.2rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
  }

  .status-ok {
    background: rgba(76, 175, 80, 0.2);
    color: var(--dnsdist-success);
  }

  .status-warning {
    background: rgba(255, 152, 0, 0.2);
    color: var(--dnsdist-warning);
  }

  .status-critical {
    background: rgba(244, 67, 54, 0.2);
    color: var(--dnsdist-error);
  }

  .status-unknown {
    background: rgba(158, 158, 158, 0.2);
    color: var(--dnsdist-secondary-text);
  }

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }

  .stat-tile {
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    transition: box-shadow 0.2s ease;
  }

  .stat-tile:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .stat-value {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
  }

  .stat-label {
    font-size: 0.75rem;
    color: var(--dnsdist-secondary-text);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .stat-icon {
    margin-bottom: 4px;
    color: var(--dnsdist-accent);
    --mdc-icon-size: 24px;
  }

  /* Gauge Styles */
  .gauge-container {
    display: flex;
    justify-content: center;
    gap: 32px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }

  .gauge {
    position: relative;
    width: 100px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .gauge-svg {
    width: 100px;
    height: 90px;
    overflow: visible;
  }

  .gauge-arc-path {
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.15));
  }

  .gauge-needle-group {
    transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .gauge-needle {
    stroke: var(--dnsdist-primary-text, #212121);
    stroke-width: 2.5;
    stroke-linecap: round;
  }

  .gauge-pivot {
    fill: var(--dnsdist-primary-text, #212121);
  }

  .gauge-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
    margin-top: 4px;
  }

  .gauge-label {
    font-size: 0.7rem;
    color: var(--dnsdist-secondary-text);
    text-transform: uppercase;
    margin-top: 2px;
  }

  /* Section Headers */
  .section-header {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--dnsdist-secondary-text);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 16px 0 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--dnsdist-divider);
  }

  /* Counters Grid */
  .counters-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }

  .counter-tile {
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    padding: 10px 8px;
    text-align: center;
  }

  .counter-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
  }

  .counter-label {
    font-size: 0.65rem;
    color: var(--dnsdist-secondary-text);
    margin-top: 2px;
    text-transform: uppercase;
  }

  /* Filter Rules */
  .filters-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 300px;
    overflow-y: auto;
  }

  .filter-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .filter-item:hover {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.05));
  }

  .filter-item.expanded {
    flex-wrap: wrap;
  }

  .filter-main {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .filter-name {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .filter-matches {
    font-size: 1rem;
    font-weight: 600;
    color: var(--dnsdist-accent);
    min-width: 50px;
    text-align: right;
  }

  .filter-action {
    display: inline-flex;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    background: rgba(3, 169, 244, 0.15);
    color: var(--dnsdist-accent);
  }

  .filter-action.drop {
    background: rgba(244, 67, 54, 0.15);
    color: var(--dnsdist-error);
  }

  .filter-action.allow {
    background: rgba(76, 175, 80, 0.15);
    color: var(--dnsdist-success);
  }

  .filter-details {
    width: 100%;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--dnsdist-divider);
    font-size: 0.8rem;
    color: var(--dnsdist-secondary-text);
  }

  .filter-detail-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
  }

  .filter-detail-label {
    font-weight: 500;
  }

  .filter-detail-value {
    font-family: monospace;
    word-break: break-all;
    text-align: right;
    max-width: 60%;
  }

  /* Action Buttons */
  .actions-container {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 16px;
  }

  .action-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background: var(--dnsdist-accent);
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s ease;
  }

  .action-button:hover {
    opacity: 0.9;
  }

  .action-button:active {
    opacity: 0.8;
  }

  .action-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-button ha-icon {
    --mdc-icon-size: 18px;
  }

  /* Compact Mode */
  :host([compact]) .gauge-container {
    gap: 12px;
  }

  :host([compact]) .gauge {
    width: 80px;
  }

  :host([compact]) .gauge-svg {
    width: 80px;
    height: 72px;
  }

  :host([compact]) .stat-tile {
    padding: 8px;
  }

  :host([compact]) .stat-value {
    font-size: 1.1rem;
  }

  /* Uptime display */
  .uptime-display {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px;
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    margin-bottom: 16px;
  }

  .uptime-value {
    font-size: 1rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
  }

  .uptime-label {
    font-size: 0.75rem;
    color: var(--dnsdist-secondary-text);
  }

  /* Empty state */
  .empty-state {
    text-align: center;
    padding: 24px;
    color: var(--dnsdist-secondary-text);
  }

  .empty-state ha-icon {
    --mdc-icon-size: 48px;
    opacity: 0.5;
    margin-bottom: 8px;
  }

  /* Loading state */
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    color: var(--dnsdist-secondary-text);
  }

  /* Confirmation dialog overlay */
  .confirm-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .confirm-dialog {
    background: var(--dnsdist-card-background);
    padding: 24px;
    border-radius: var(--dnsdist-border-radius);
    max-width: 320px;
    text-align: center;
  }

  .confirm-title {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--dnsdist-primary-text);
  }

  .confirm-message {
    font-size: 0.9rem;
    color: var(--dnsdist-secondary-text);
    margin-bottom: 16px;
  }

  .confirm-buttons {
    display: flex;
    gap: 8px;
    justify-content: center;
  }

  .confirm-cancel {
    background: var(--dnsdist-divider);
    color: var(--dnsdist-primary-text);
  }

  .confirm-confirm {
    background: var(--dnsdist-error);
  }
`;n`
  :host {
    display: block;
  }

  .form-group {
    margin-bottom: 16px;
  }

  .form-label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--primary-text-color);
    margin-bottom: 4px;
  }

  .form-hint {
    font-size: 0.75rem;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }

  ha-textfield,
  ha-select {
    display: block;
    width: 100%;
  }

  ha-formfield {
    display: block;
    margin-bottom: 8px;
  }
`;let gt=class extends at{setConfig(t){this._config={...t}}_updateConfig(t,e){if(!this._config)return;const i={...this._config,[t]:e};this._config=i,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:i},bubbles:!0,composed:!0}))}_getAvailablePrefixes(){if(!this.hass?.states)return[];const t=new Set,e=[/^sensor\.(.+?)_total_queries$/,/^sensor\.(.+?)_uptime$/,/^sensor\.(.+?)_cpu_usage$/,/^sensor\.(.+?)_responses$/,/^sensor\.(.+?)_filter_/,/^sensor\.(.+?)_dynblock_/];for(const i of Object.keys(this.hass.states))for(const s of e){const e=i.match(s);if(e){t.add(e[1]);break}}return Array.from(t).sort()}render(){if(!this.hass||!this._config)return F`<div>Loading...</div>`;const t=this._getAvailablePrefixes();return F`
      <div class="form-row">
        <label for="entity_prefix">Entity Prefix *</label>
        <input
          type="text"
          id="entity_prefix"
          .value=${this._config.entity_prefix||""}
          @input=${t=>{const e=t.target.value;this._updateConfig("entity_prefix",e)}}
          placeholder="e.g., dns1"
        />
        ${t.length>0?F`
              <div class="form-hint">Click to select:</div>
              <div class="prefix-chips">
                ${t.map(t=>F`
                    <button
                      type="button"
                      class="prefix-chip"
                      @click=${()=>this._updateConfig("entity_prefix",t)}
                    >
                      ${t}
                    </button>
                  `)}
              </div>
            `:F`<div class="form-hint">No dnsdist entities detected</div>`}
      </div>

      <div class="form-row">
        <label for="title">Card Title</label>
        <input
          type="text"
          id="title"
          .value=${this._config.title||""}
          @input=${t=>{const e=t.target.value;this._updateConfig("title",e)}}
          placeholder="Optional custom title"
        />
        <div class="form-hint">
          Leave empty to use the entity prefix as title
        </div>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${!1!==this._config.show_filters}
            @change=${t=>{const e=t.target.checked;this._updateConfig("show_filters",e)}}
          />
          Show Filtering Rules
        </label>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${!1!==this._config.show_dynamic_rules}
            @change=${t=>{const e=t.target.checked;this._updateConfig("show_dynamic_rules",e)}}
          />
          Show Dynamic Rules
        </label>
        <div class="form-hint">
          Display dynamic blocks (rate limiting, DoS protection)
        </div>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${!1!==this._config.show_actions}
            @change=${t=>{const e=t.target.checked;this._updateConfig("show_actions",e)}}
          />
          Show Action Buttons
        </label>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${!0===this._config.compact}
            @change=${t=>{const e=t.target.checked;this._updateConfig("compact",e)}}
          />
          Compact Mode
        </label>
        <div class="form-hint">
          Use smaller sizes for sidebar placement
        </div>
      </div>
    `}};var mt;gt.styles=n`
    :host {
      display: block;
    }
    .form-row {
      margin-bottom: 16px;
    }
    .form-row label {
      display: block;
      margin-bottom: 4px;
      font-weight: 500;
    }
    .form-hint {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }
    ha-textfield {
      display: block;
      width: 100%;
    }
    ha-formfield {
      display: block;
      padding: 8px 0;
    }
    .prefix-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .prefix-chip {
      padding: 4px 12px;
      border-radius: 16px;
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-size: 12px;
      cursor: pointer;
      border: none;
    }
    .prefix-chip:hover {
      opacity: 0.8;
    }
    input[type="text"] {
      width: 100%;
      padding: 8px 12px;
      border: 1px solid var(--divider-color, #ccc);
      border-radius: 4px;
      font-size: 14px;
      box-sizing: border-box;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #000);
    }
    input[type="text"]:focus {
      outline: none;
      border-color: var(--primary-color);
    }
    input[type="checkbox"] {
      margin-right: 8px;
      width: 18px;
      height: 18px;
      cursor: pointer;
    }
    label {
      display: flex;
      align-items: center;
      cursor: pointer;
    }
  `,t([pt({attribute:!1})],gt.prototype,"hass",void 0),t([ut()],gt.prototype,"_config",void 0),gt=t([lt("dnsdist-card-editor")],gt),window.customCards=window.customCards||[],window.customCards.push({type:"dnsdist-card",name:"dnsdist Card",description:"Display dnsdist DNS server metrics and filtering rules",preview:!0});let _t=mt=class extends at{constructor(){super(...arguments),this._expandedFilters=new Set,this._expandedDynamic=new Set,this._showConfirm=!1,this._confirmAction=null}static getConfigElement(){return document.createElement("dnsdist-card-editor")}static getStubConfig(){return{entity_prefix:"dnsdist",show_filters:!0,show_dynamic_rules:!0,show_actions:!0}}setConfig(t){this._config={show_graphs:!1,show_filters:!0,show_dynamic_rules:!0,show_actions:!0,compact:!1,...t,entity_prefix:t.entity_prefix||""}}updated(t){super.updated(t),this._config?.compact?this.setAttribute("compact",""):this.removeAttribute("compact")}_getEntityId(t){const e=this._config.entity_prefix,i=mt.METRIC_TO_ENTITY[t]||[t],s=[e,`${e}_${e}`];for(const t of s)for(const e of i){const i=`sensor.${t}_${e}`;if(this.hass?.states?.[i])return i}return`sensor.${e}_${i[0]}`}_getEntity(t){const e=this._getEntityId(t);return e?this.hass?.states?.[e]:void 0}_getEntityValue(t){const e=this._getEntity(t);if(!e)return null;const i=e.state;return"unavailable"===i||"unknown"===i?null:i}_getNumericValue(t){const e=this._getEntityValue(t);if(null===e)return null;const i=parseFloat(String(e));return isNaN(i)?null:i}_formatNumber(t){return null===t?"-":t>=1e6?`${(t/1e6).toFixed(1)}M`:t>=1e3?`${(t/1e3).toFixed(1)}K`:t.toLocaleString()}_getSecurityStatus(){const t=this._getEntityValue("security_status");return t?String(t).toLowerCase():"unknown"}_getSecurityStatusClass(){const t=this._getSecurityStatus();return"ok"===t||"secure"===t?"status-ok":"warning"===t?"status-warning":"critical"===t?"status-critical":"status-unknown"}_getSecurityLabel(){const t=this._getEntity("security_status");return t?.attributes?.status_label||this._getSecurityStatus().toUpperCase()}_getUptimeDisplay(){const t=this._getEntity("uptime");if(!t)return"-";const e=t.attributes?.human_readable;if(e)return e;const i=this._getNumericValue("uptime");if(null===i)return"-";const s=Math.floor(i/86400),r=Math.floor(i%86400/3600),o=Math.floor(i%3600/60);return`${s}d ${r.toString().padStart(2,"0")}h ${o.toString().padStart(2,"0")}m`}_getFilterEntities(){if(!this.hass?.states)return[];const t=this._config.entity_prefix,e=t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),i=new RegExp(`^sensor\\.(${e}_)?${e}[_\\s]?filter`,"i"),s=[];for(const e of Object.keys(this.hass.states)){if(!e.startsWith("sensor."))continue;const r=this.hass.states[e],o=r.attributes?.friendly_name||"",n=i.test(e),a=t.toLowerCase().replace(/_/g," "),c=o.toLowerCase().includes(" filter ")&&(o.toLowerCase().startsWith(a)||o.toLowerCase().startsWith(`${a} ${a}`)),l=(void 0!==r.attributes?.action||void 0!==r.attributes?.rule&&void 0!==r.attributes?.enabled)&&(e.toLowerCase().includes(t.toLowerCase())||o.toLowerCase().includes(t.toLowerCase().replace(/_/g," ")));if(!n&&!c&&!l)continue;const d=parseInt(r.state,10),h={matches:isNaN(d)?0:d,id:r.attributes?.id,uuid:r.attributes?.uuid,name:this._extractRuleName(r),action:r.attributes?.action,rule:r.attributes?.rule,type:r.attributes?.type,enabled:r.attributes?.enabled,bypass:r.attributes?.bypass,sources:r.attributes?.sources};s.push({entity:r,rule:h})}return s.sort((t,e)=>e.rule.matches-t.rule.matches)}_extractRuleName(t){const e=t.attributes?.friendly_name;if(e){const t=e.match(/Filter (.+)$/);if(t)return t[1]}const i=t.entity_id.match(/_filter_(.+)$/);return i?i[1].replace(/_/g," "):"Unknown Rule"}_toggleFilterExpand(t){const e=new Set(this._expandedFilters);e.has(t)?e.delete(t):e.add(t),this._expandedFilters=e}_getDynamicRuleEntities(){if(!this.hass?.states)return[];const t=this._config.entity_prefix,e=t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),i=new RegExp(`^sensor\\.(${e}_)?${e}[_\\s]?dynblock`,"i"),s=[];for(const e of Object.keys(this.hass.states)){if(!e.startsWith("sensor."))continue;const r=this.hass.states[e],o=r.attributes?.friendly_name||"",n=i.test(e),a=t.toLowerCase().replace(/_/g," "),c=o.toLowerCase().includes(" dynblock ")&&(o.toLowerCase().startsWith(a)||o.toLowerCase().startsWith(`${a} ${a}`)),l=(void 0!==r.attributes?.network||void 0!==r.attributes?.reason&&void 0!==r.attributes?.seconds)&&(e.toLowerCase().includes(t.toLowerCase())||o.toLowerCase().includes(t.toLowerCase().replace(/_/g," ")));if(!n&&!c&&!l)continue;const d=parseInt(r.state,10),h={blocks:isNaN(d)?0:d,network:r.attributes?.network,reason:r.attributes?.reason,action:r.attributes?.action,seconds:r.attributes?.seconds,ebpf:r.attributes?.ebpf,warning:r.attributes?.warning,sources:r.attributes?.sources};s.push({entity:r,rule:h})}return s.sort((t,e)=>e.rule.blocks-t.rule.blocks)}_extractDynamicRuleName(t){const e=t.attributes?.friendly_name;if(e){const t=e.match(/Dynblock (.+)$/);if(t)return t[1]}const i=t.attributes?.network;if(i)return i;const s=t.entity_id.match(/_dynblock_(.+)$/);return s?s[1].replace(/_/g,"."):"Unknown"}_toggleDynamicExpand(t){const e=new Set(this._expandedDynamic);e.has(t)?e.delete(t):e.add(t),this._expandedDynamic=e}_formatTimeRemaining(t){if(void 0===t||t<=0)return"-";const e=Math.floor(t/60),i=t%60;return e>0?`${e}m ${i}s`:`${i}s`}_getActionClass(t){if(!t)return"";const e=t.toLowerCase();return e.includes("drop")||e.includes("refuse")?"drop":e.includes("allow")||e.includes("pool")?"allow":""}async _clearCache(){const t=this._config.entity_prefix,e=`button.${t}_clear_cache`;this.hass.states[e]?await this.hass.callService("button","press",{entity_id:e}):await this.hass.callService("dnsdist","clear_cache",{host:t})}_showClearCacheConfirm(){this._confirmAction=()=>this._clearCache(),this._showConfirm=!0}_confirmDialogAction(){this._confirmAction&&this._confirmAction(),this._hideConfirm()}_hideConfirm(){this._showConfirm=!1,this._confirmAction=null}_renderGaugeGreenToRed(t,e){const i=null!==t?Math.min(100,Math.max(0,t)):0;return F`
      <div class="gauge">
        <svg class="gauge-svg" viewBox="0 0 100 100">
          <path d="M 21.72 78.28 A 40 40 0 0 1 10.77 57.80" fill="none" stroke="#4caf50" stroke-width="8"/>
          <path d="M 10.77 57.80 A 40 40 0 0 1 13.04 34.69" fill="none" stroke="#8bc34a" stroke-width="8"/>
          <path d="M 13.04 34.69 A 40 40 0 0 1 27.78 16.74" fill="none" stroke="#cddc39" stroke-width="8"/>
          <path d="M 27.78 16.74 A 40 40 0 0 1 50.00 10.00" fill="none" stroke="#ffeb3b" stroke-width="8"/>
          <path d="M 50.00 10.00 A 40 40 0 0 1 72.22 16.74" fill="none" stroke="#ffc107" stroke-width="8"/>
          <path d="M 72.22 16.74 A 40 40 0 0 1 86.96 34.69" fill="none" stroke="#ff9800" stroke-width="8"/>
          <path d="M 86.96 34.69 A 40 40 0 0 1 89.23 57.80" fill="none" stroke="#ff5722" stroke-width="8"/>
          <path d="M 89.23 57.80 A 40 40 0 0 1 78.28 78.28" fill="none" stroke="#f44336" stroke-width="8"/>
          <g class="gauge-needle-group" style="transform: rotate(${i/100*270-135}deg); transform-origin: 50px 50px;">
            <line class="gauge-needle" x1="50" y1="50" x2="50" y2="16" />
          </g>
          <circle class="gauge-pivot" cx="50" cy="50" r="4" />
        </svg>
        <div class="gauge-value">${null!==t?`${t.toFixed(0)}%`:"-"}</div>
        <div class="gauge-label">${e}</div>
      </div>
    `}_renderGaugeRedToGreen(t,e){const i=null!==t?Math.min(100,Math.max(0,t)):0;return F`
      <div class="gauge">
        <svg class="gauge-svg" viewBox="0 0 100 100">
          <path d="M 21.72 78.28 A 40 40 0 0 1 10.77 57.80" fill="none" stroke="#f44336" stroke-width="8"/>
          <path d="M 10.77 57.80 A 40 40 0 0 1 13.04 34.69" fill="none" stroke="#ff5722" stroke-width="8"/>
          <path d="M 13.04 34.69 A 40 40 0 0 1 27.78 16.74" fill="none" stroke="#ff9800" stroke-width="8"/>
          <path d="M 27.78 16.74 A 40 40 0 0 1 50.00 10.00" fill="none" stroke="#ffc107" stroke-width="8"/>
          <path d="M 50.00 10.00 A 40 40 0 0 1 72.22 16.74" fill="none" stroke="#ffeb3b" stroke-width="8"/>
          <path d="M 72.22 16.74 A 40 40 0 0 1 86.96 34.69" fill="none" stroke="#cddc39" stroke-width="8"/>
          <path d="M 86.96 34.69 A 40 40 0 0 1 89.23 57.80" fill="none" stroke="#8bc34a" stroke-width="8"/>
          <path d="M 89.23 57.80 A 40 40 0 0 1 78.28 78.28" fill="none" stroke="#4caf50" stroke-width="8"/>
          <g class="gauge-needle-group" style="transform: rotate(${i/100*270-135}deg); transform-origin: 50px 50px;">
            <line class="gauge-needle" x1="50" y1="50" x2="50" y2="16" />
          </g>
          <circle class="gauge-pivot" cx="50" cy="50" r="4" />
        </svg>
        <div class="gauge-value">${null!==t?`${t.toFixed(0)}%`:"-"}</div>
        <div class="gauge-label">${e}</div>
      </div>
    `}_renderCounterTile(t,e,i){const s=this._getNumericValue(e);return F`
      <div class="counter-tile">
        <ha-icon icon="${i}"></ha-icon>
        <div class="counter-value">${this._formatNumber(s)}</div>
        <div class="counter-label">${t}</div>
      </div>
    `}_renderFilterItem(t,e){const i=this._expandedFilters.has(t);return F`
      <div
        class="filter-item ${i?"expanded":""}"
        @click=${()=>this._toggleFilterExpand(t)}
      >
        <div class="filter-main">
          <span class="filter-name">${e.name||"Unnamed Rule"}</span>
          ${e.action?F`<span class="filter-action ${this._getActionClass(e.action)}">${e.action}</span>`:V}
        </div>
        <span class="filter-matches">${this._formatNumber(e.matches)}</span>

        ${i?F`
              <div class="filter-details">
                ${e.rule?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Pattern:</span>
                        <span class="filter-detail-value">${e.rule}</span>
                      </div>
                    `:V}
                ${e.type?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Type:</span>
                        <span class="filter-detail-value">${e.type}</span>
                      </div>
                    `:V}
                ${void 0!==e.enabled?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Enabled:</span>
                        <span class="filter-detail-value">${e.enabled?"Yes":"No"}</span>
                      </div>
                    `:V}
                ${void 0!==e.id?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">ID:</span>
                        <span class="filter-detail-value">${e.id}</span>
                      </div>
                    `:V}
              </div>
            `:V}
      </div>
    `}_renderDynamicRuleItem(t,e){const i=this._expandedDynamic.has(t),s=e.network||this._extractDynamicRuleName(this.hass.states[t]);return F`
      <div
        class="filter-item ${i?"expanded":""}"
        @click=${()=>this._toggleDynamicExpand(t)}
      >
        <div class="filter-main">
          <span class="filter-name">${s}</span>
          ${e.action?F`<span class="filter-action ${this._getActionClass(e.action)}">${e.action}</span>`:V}
        </div>
        <span class="filter-matches">${this._formatNumber(e.blocks)}</span>

        ${i?F`
              <div class="filter-details">
                ${e.reason?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Reason:</span>
                        <span class="filter-detail-value">${e.reason}</span>
                      </div>
                    `:V}
                ${void 0!==e.seconds&&e.seconds>0?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Time Left:</span>
                        <span class="filter-detail-value">${this._formatTimeRemaining(e.seconds)}</span>
                      </div>
                    `:V}
                ${void 0!==e.ebpf?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">eBPF:</span>
                        <span class="filter-detail-value">${e.ebpf?"Yes":"No"}</span>
                      </div>
                    `:V}
                ${void 0!==e.warning&&e.warning?F`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Warning:</span>
                        <span class="filter-detail-value">Yes</span>
                      </div>
                    `:V}
              </div>
            `:V}
      </div>
    `}_renderConfirmDialog(){return this._showConfirm?F`
      <div class="confirm-overlay" @click=${this._hideConfirm}>
        <div class="confirm-dialog" @click=${t=>t.stopPropagation()}>
          <div class="confirm-title">Clear Cache?</div>
          <div class="confirm-message">
            This will clear the DNS cache on ${this._config.title||this._config.entity_prefix}.
          </div>
          <div class="confirm-buttons">
            <button class="action-button confirm-cancel" @click=${this._hideConfirm}>
              Cancel
            </button>
            <button class="action-button confirm-confirm" @click=${this._confirmDialogAction}>
              Clear
            </button>
          </div>
        </div>
      </div>
    `:V}render(){if(!this._config||!this.hass)return F`<ha-card><div class="loading">Loading...</div></ha-card>`;if(!this._config.entity_prefix)return F`
        <ha-card>
          <div class="empty-state">
            <ha-icon icon="mdi:dns"></ha-icon>
            <div>Please configure the entity prefix</div>
          </div>
        </ha-card>
      `;const t=this._config.title||this._config.entity_prefix,e=this._getNumericValue("cpu"),i=this._getNumericValue("cache_hit_rate"),s=this._config.show_filters?this._getFilterEntities():[],r=this._config.show_dynamic_rules?this._getDynamicRuleEntities():[];return F`
      <ha-card>
        <!-- Header -->
        <div class="card-header">
          <div class="card-title">
            <ha-icon icon="mdi:dns"></ha-icon>
            ${t}
          </div>
          <span class="status-badge ${this._getSecurityStatusClass()}">
            ${this._getSecurityLabel()}
          </span>
        </div>

        <!-- Gauges -->
        <div class="gauge-container">
          ${this._renderGaugeGreenToRed(e,"CPU")}
          ${this._renderGaugeRedToGreen(i,"Cache Hit")}
        </div>

        <!-- Uptime -->
        <div class="uptime-display">
          <ha-icon icon="mdi:timer-outline"></ha-icon>
          <span class="uptime-label">Uptime:</span>
          <span class="uptime-value">${this._getUptimeDisplay()}</span>
        </div>

        <!-- Traffic Counters -->
        <div class="section-header">Traffic Counters</div>
        <div class="counters-grid">
          ${this._renderCounterTile("Queries","queries","mdi:dns")}
          ${this._renderCounterTile("Responses","responses","mdi:send")}
          ${this._renderCounterTile("Drops","drops","mdi:cancel")}
          ${this._renderCounterTile("Rule Drops","rule_drop","mdi:shield-off-outline")}
          ${this._renderCounterTile("Errors","downstream_errors","mdi:alert-circle")}
        </div>

        <!-- Request Rates -->
        <div class="section-header">Request Rates</div>
        <div class="stats-grid">
          <div class="stat-tile">
            <ha-icon class="stat-icon" icon="mdi:chart-line"></ha-icon>
            <div class="stat-value">${this._formatNumber(this._getNumericValue("req_per_hour"))}</div>
            <div class="stat-label">Per Hour</div>
          </div>
          <div class="stat-tile">
            <ha-icon class="stat-icon" icon="mdi:chart-areaspline"></ha-icon>
            <div class="stat-value">${this._formatNumber(this._getNumericValue("req_per_day"))}</div>
            <div class="stat-label">Per Day</div>
          </div>
        </div>

        <!-- Filtering Rules (only shown if rules exist) -->
        ${this._config.show_filters&&s.length>0?F`
              <div class="section-header">Filtering Rules (${s.length})</div>
              <div class="filters-list">
                ${s.map(({entity:t,rule:e})=>this._renderFilterItem(t.entity_id,e))}
              </div>
            `:V}

        <!-- Dynamic Rules (only shown if rules exist) -->
        ${this._config.show_dynamic_rules&&r.length>0?F`
              <div class="section-header">Dynamic Rules (${r.length})</div>
              <div class="filters-list">
                ${r.map(({entity:t,rule:e})=>this._renderDynamicRuleItem(t.entity_id,e))}
              </div>
            `:V}

        <!-- Actions -->
        ${this._config.show_actions?F`
              <div class="actions-container">
                <button class="action-button" @click=${this._showClearCacheConfirm}>
                  <ha-icon icon="mdi:database-refresh"></ha-icon>
                  Clear Cache
                </button>
              </div>
            `:V}

        ${this._renderConfirmDialog()}
      </ha-card>
    `}getCardSize(){let t=3;if(t+=2,t+=2,this._config?.show_filters){const e=this._getFilterEntities().length;t+=Math.min(4,Math.ceil(e/2)+1)}if(this._config?.show_dynamic_rules){const e=this._getDynamicRuleEntities().length;t+=Math.min(4,Math.ceil(e/2)+1)}return this._config?.show_actions&&(t+=1),t}};_t.styles=ft,_t.METRIC_TO_ENTITY={queries:["total_queries","queries"],responses:["responses"],drops:["dropped_queries","drops"],rule_drop:["rule_drops","rule_drop"],downstream_errors:["downstream_send_errors","downstream_errors"],cache_hits:["cache_hits"],cache_misses:["cache_misses"],cache_hit_rate:["cache_hit_rate","cachehit"],cpu:["cpu_usage","cpu"],uptime:["uptime"],req_per_hour:["requests_per_hour_last_hour","req_per_hour"],req_per_day:["requests_per_day_last_24h","req_per_day"],security_status:["security_status"]},t([pt({attribute:!1})],_t.prototype,"hass",void 0),t([ut()],_t.prototype,"_config",void 0),t([ut()],_t.prototype,"_expandedFilters",void 0),t([ut()],_t.prototype,"_expandedDynamic",void 0),t([ut()],_t.prototype,"_showConfirm",void 0),t([ut()],_t.prototype,"_confirmAction",void 0),_t=mt=t([lt("dnsdist-card")],_t);export{_t as DnsdistCard};

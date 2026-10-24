"use client"

import Left from "./left";
import Right from "./right";

const Client = () => {
    return <>
    <div className="flex h-screen">
        <Left />
        <Right />
    </div>
    </>;
}
 
export default Client;
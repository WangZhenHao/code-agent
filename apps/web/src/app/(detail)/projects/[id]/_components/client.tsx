"use client"

import './page.css'

import Left from "./left"
import Right from "./right"

const Client = () => {
    return <>
    <div className="h-screen flex bg-sidebar">
        <Left />
        <Right />
    </div>
    </>;
}

export default Client;

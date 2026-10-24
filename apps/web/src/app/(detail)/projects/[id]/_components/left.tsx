import { Composer, TypeParmas } from "@/app/(home)/_components/composer";
import { useState } from "react";

const Left = () => {
  const [prompt, setPrompt] = useState("");
  const handleSumbit = async (prompt: TypeParmas) => {
    console.log(prompt);
  };
  return (
    <div
      style={{ width: "440px" }}
      className="border-r pl-3 pr-2 flex flex-col h-full"
    >
      <Composer
        prompt={prompt}
        onPromptChange={setPrompt}
        onSubmit={handleSumbit}
      />
    </div>
  );
};

export default Left;

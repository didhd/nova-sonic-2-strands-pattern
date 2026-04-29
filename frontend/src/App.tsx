import { useState } from "react";
import TopNavigation from "@cloudscape-design/components/top-navigation";
import AppLayout from "@cloudscape-design/components/app-layout";
import SideNavigation from "@cloudscape-design/components/side-navigation";
import SpeechToSpeech from "./components/SpeechToSpeech";

export default function App() {
  const [navOpen, setNavOpen] = useState(true);

  return (
    <>
      <TopNavigation
        identity={{
          href: "/",
          title: "Nova Sonic 2 + Strands Agent",
        }}
        utilities={[
          {
            type: "button",
            text: "Documentation",
            href: "https://strandsagents.com",
            external: true,
          },
          {
            type: "button",
            text: "Workshop",
            href: "https://catalog.workshops.aws/workshops/5238419f-1337-4e0f-8cd7-02239486c40d",
            external: true,
          },
        ]}
      />
      <AppLayout
        navigationOpen={navOpen}
        onNavigationChange={({ detail }) => setNavOpen(detail.open)}
        navigation={
          <SideNavigation
            header={{ href: "/", text: "Nova Sonic Demo" }}
            items={[
              { type: "link", text: "Speech-to-Speech", href: "/" },
              { type: "divider" },
              {
                type: "link",
                text: "Architecture",
                href: "https://catalog.workshops.aws/workshops/5238419f-1337-4e0f-8cd7-02239486c40d/en-US/02-repeatable-pattern/03-strands",
                external: true,
              },
              {
                type: "link",
                text: "Strands Agents",
                href: "https://strandsagents.com",
                external: true,
              },
              {
                type: "link",
                text: "Nova Sonic Docs",
                href: "https://docs.aws.amazon.com/nova/latest/userguide/speech.html",
                external: true,
              },
            ]}
          />
        }
        content={<SpeechToSpeech />}
        toolsHide={true}
      />
    </>
  );
}
